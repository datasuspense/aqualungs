import base64
import json
from pathlib import Path
import random
import time
import sqlite3
from typing import Any, Optional

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from omegaconf import DictConfig
from tqdm import tqdm

from aqualungs.models import Article
from aqualungs.extract import Extractor

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']


class Downloader:
    def __init__(
            self,
            config: DictConfig
    ):
        self.articles: list[Article] = []

        self.email = config.email

        self.headers = config.downloader.headers
        self.max_messages = config.downloader.max_messages
        self.timeout = config.downloader.timeout
        self.delay = config.downloader.delay_seconds
        self.output_dir = config.downloader.output_dir

        self.creds: Optional[Credentials] = None

        self.db_path = Path(config.database.path)
        self.init_db()

    def authorize(self) -> None:
        token_file = Path('../data/token.json')
        if token_file.exists():
            self.creds = Credentials.from_authorized_user_file('../data/token.json', SCOPES)
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file('../data/credentials.json', SCOPES)
                self.creds = flow.run_local_server(port=10228)
            token_file.parent.mkdir(parents=True, exist_ok=True)
            token_file.write_text(self.creds.to_json(), encoding='utf-8')

    def get_messages(self) -> None:
        self.authorize()

        try:
            # Call the Gmail API
            service = build('gmail', 'v1', credentials=self.creds)
            results = service.users().messages().list(
                userId='me',
                q=f'from:{self.email.sender}',
                maxResults=self.max_messages).execute()
            messages = results.get('messages', [])
            if not messages:
                print('No messages found.')
                return
            else:
                print(f'Found {len(messages)} messages.')

            extractor = Extractor()
            path = Path('../data/messages/')
            path.mkdir(parents=True, exist_ok=True)
            for msg in tqdm(messages, desc='Downloading messages', unit='message'):
                message = service.users().messages().get(userId='me', id=msg['id'], format='full').execute()

                message_created_at = extractor.parse_datetime(self.extract_date_from_header(message))
                message_path = path.joinpath(f"{message_created_at.replace(':', '-')} - {message['id']}.txt")
                if message_path.exists():
                    continue

                if 'attachmentId' in message['payload']['body'] and 'data' not in message['payload']['body']:
                    attachment = service.users().messages().attachments().get(
                        userId='me', messageId=msg['id'], id=message['payload']['body']['attachmentId']
                    ).execute()
                    message['payload']['body']['data'] = attachment['data']
                try:
                    text = self.extract_data(message)
                except Exception as e:
                    print(f"Error decoding message {msg['id']}: {e}")
                    continue

                self.articles.extend(extractor.extract(text))
                message_path.write_text(text, encoding='utf-8')

            self.save_articles()

        except HttpError as error:
            print(f'An error occurred: {error}')

    def batch_urls(self, offset: int = 0, limit: int = 20):
        i = offset
        print(f'{len(self.articles)} articles')
        while i < len(self.articles):
            urls = []
            for article in self.articles[i:i+limit]:
                urls.append(article.url.encoded_string())
            print(f"Batch{i}: {', '.join(urls)}")
            i += limit

    def download_pdfs(self) -> None:
        for article in tqdm(self.articles, desc='Downloading PDFs', unit='article'):
            path = Path(self.output_dir)
            path.mkdir(parents=True, exist_ok=True)
            file_path = path.joinpath(f"{article.arxiv_id}. {article.title.replace('/', '\\/')}.pdf")

            if Path.exists(file_path):
                print(f"{article.url} skipped, already exists.")
                continue

            try:
                print(f"Downloading: {article.url}...")
                response = requests.get(article.url, headers=self.headers, timeout=self.timeout)
                if response.status_code == 200:
                    file_path.write_bytes(response.content)
                    print(f"Document saved: {file_path}")
                else:
                    print(f"Download error {article.arxiv_id}: status code {response.status_code}")

                delay = random.uniform(self.delay.min, self.delay.max)
                print(f"Delay {delay:.2f} seconds before next file...")
                time.sleep(delay)

            except Exception as e:
                print(f"Error occurred {article.arxiv_id}: {e}")

    @staticmethod
    def extract_data(message: dict) -> str:
        message_data = message['payload']['body']['data'].strip()
        padding = "=" * (-len(message_data) % 4)
        text = base64.urlsafe_b64decode(message_data + padding).decode("utf-8", errors="replace")
        return text

    @staticmethod
    def extract_date_from_header(message: dict[str, Any]) -> str:
        s = [
            header['value']
            for header in message['payload']['headers']
            if header['name'] == 'Date'
        ][0]
        return s


    def init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            path = Path('db/create_table_articles.sql')
            sql_query = path.read_text()
            conn.execute(sql_query)
            conn.commit()

    def save_articles(self) -> None:
        if not self.articles:
            return
        print(f"Saving {len(self.articles)} articles to database...")
        with sqlite3.connect(self.db_path) as conn:
            path = Path('db/insert_articles.sql')
            sql_query = path.read_text()
            cursor = conn.cursor()
            cursor.executemany(
                sql_query,
                [
                    (
                        a.arxiv_id,
                        a.title,
                        json.dumps(a.authors, ensure_ascii=False),
                        a.created_at,
                        a.annotation,
                        json.dumps(a.subjects, ensure_ascii=False),
                        str(a.url),
                        json.dumps([str(u) for u in a.github_urls], ensure_ascii=False),
                        json.dumps([str(u) for u in a.other_urls], ensure_ascii=False),
                        int(a.is_updated),
                    )
                    for a in self.articles
                ],
            )
            print(f"Saved {cursor.rowcount} new articles to database.")
            conn.commit()
