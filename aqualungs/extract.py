from datetime import datetime
import re

from aqualungs.models import Article


class Extractor:
    def __init__(self):
        self.re_patterns: dict = {
            'timeframe': re.compile(
                r"received\s+from\s+(?P<from>.+?)\s+to\s+(?P<to>.+?)\s*$",
                re.IGNORECASE | re.MULTILINE),
            'arxiv_id': re.compile(r"^arXiv:(?P<id>\S+)", re.MULTILINE),
            'entry_start': re.compile(r"^-{20,}\s*\n\\\\\s*\n(?=arXiv:)", re.MULTILINE),
            'date': re.compile(r"^Date:\s*(?P<date>.+?)\s*(?:\(|$)", re.MULTILINE),
            'replaced': re.compile(
                r"^replaced\s+with\s+revised\s+version\s+(?P<date>.+?)\s*(?:\(|$)",
                re.IGNORECASE | re.MULTILINE),
            'title': re.compile(r"^Title:\s*(?P<title>.*)$", re.MULTILINE),
            'authors': re.compile(r"^Authors:\s*(?P<authors>.*)$", re.MULTILINE),
            'categories': re.compile(r"^Categories:\s*(?P<cats>.*)$", re.MULTILINE),
            'url': re.compile(r"^\\\\\s*\(\s*(?P<url>https?://\S+)", re.MULTILINE),
            'github_url': re.compile(
                r"https?://(?:www\.)?github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/\S*)?",
                re.IGNORECASE | re.MULTILINE
            )
        }

    def extract(self, text: str) -> list[Article]:
        articles: list[Article] = []
        blocks = self.split_articles(text)
        for block in blocks:
            article = self.parse_article(block)
            articles.append(article)
        return articles

    def extract_timeframe(self, text: str) -> tuple[str, str]:
        match = self.re_patterns['timeframe'].search(text)
        if not match:
            return '', ''
        from_raw = match.group('from').strip()
        to_raw = match.group('to').strip()
        ts_from = self.parse_datetime(from_raw)
        ts_to = self.parse_datetime(to_raw)
        return ts_from, ts_to

    def split_articles(self, text: str) -> list[str]:
        # Find positions of entry-start markers
        starts = [match.end() for match in self.re_patterns['entry_start'].finditer(text)]
        if not starts:
            return []

        blocks = []
        for i, start in enumerate(starts):
            end = starts[i + 1] if i + 1 < len(starts) else len(text)
            block = text[start:end].strip()
            if self.re_patterns['arxiv_id'].search(block):
                blocks.append(block)
        return blocks

    def parse_article(self, text: str) -> Article:
        # ArXiv ID
        match = self.re_patterns['arxiv_id'].search(text)
        if not match:
            raise ValueError("No arXiv ID found in block.")
        arxiv_id = match.group('id')

        # Date
        match = self.re_patterns['replaced'].search(text)
        if match:
            is_updated = 1
            ts = self.parse_datetime(match.group('date'))
        else:
            is_updated = 0
            match = self.re_patterns['date'].search(text)
            ts = self.parse_datetime(match.group('date')) if match else ''

        # Title/Authors can wrap
        title = self.unwrap_field_lines(text, 'Title')
        if not title:
            match = self.re_patterns['title'].search(text)
            title = match.group('title').strip() if match else ''
        authors_raw = self.unwrap_field_lines(text, 'Authors')
        if not authors_raw:
            match = self.re_patterns['authors'].search(text)
            authors_raw = match.group('authors').strip() if match else ''
        authors = self.parse_authors(authors_raw) if authors_raw else []

        # Categories
        match = self.re_patterns['categories'].search(text)
        categories = match.group('cats').strip().split() if match else []

        # URL
        match = self.re_patterns['url'].search(text)
        url = match.group('url').strip() if match else f'https://arxiv.org/abs/{arxiv_id}'
        url = url.replace('/abs/', '/pdf/')

        # GitHub URLs
        match = self.re_patterns['github_url'].findall(text)
        github_urls = [url.strip() for url in match]

        annotation = self.parse_annotation(text)

        article = Article(
            arxiv_id=arxiv_id,
            title=title,
            authors=authors,
            created_at=ts,
            annotation=annotation,
            subjects=categories,
            url=url,
            github_urls=github_urls,
            is_updated=is_updated
        )
        return article

    @staticmethod
    def parse_datetime(text: str) -> str:
        s = text.strip()
        # Remove trailing stuff like "(6610kb)" if present
        s = re.sub(r"\s*\(.*?\)\s*$", "", s).strip()
        # Normalize multiple spaces
        s = re.sub(r"\s+", " ", s)
        # Try common formats
        fmts = [
            "%a, %d %b %Y %H:%M:%S %Z",  # Wed, 25 Feb 2026 19:31:58 GMT
            "%a %d %b %y %H:%M:%S %Z",  # Wed 25 Feb 26 19:00:00 GMT
            "%a %d %b %Y %H:%M:%S %Z",  # Wed 25 Feb 2026 19:00:00 GMT
            "%a, %d %b %Y %H:%M:%S",
            "%a %d %b %Y %H:%M:%S",
            "%a, %d %b %Y %H:%M:%S %z"  # Fri, 27 Feb 2026 01:02:08 -0500
        ]
        output_error = None
        for fmt in fmts:
            try:
                ts = datetime.strptime(s, fmt).strftime('%Y-%m-%d %H:%M:%S')
                return ts
            except Exception as e:
                output_error = e

        raise ValueError(f"Cannot parse date string: {text!r}. Error: {output_error}")

    @staticmethod
    def unwrap_field_lines(text: str, field_name: str) -> str:
        pattern = re.compile(
            rf"^{re.escape(field_name)}:\s*(?P<first>.*)\n(?P<cont>(?:[ \t].*\n)*)",
            re.MULTILINE
        )
        match = pattern.search(text)
        if not match:
            return ''
        first = match.group('first').rstrip()
        cont = match.group('cont') or ''
        cont_lines = [ln.strip() for ln in cont.splitlines() if ln.strip()]
        full = ' '.join([first] + cont_lines).strip()
        return re.sub(r'\s+', ' ', full)

    @staticmethod
    def parse_authors(text: str) -> list[str]:
        """
        Authors can be 'A and B and C' or 'A, B' or mix.
        We'll split on 'and' first, then clean commas inside pieces if needed.
        """
        s = re.sub(r"\s+", " ", text.strip())
        parts = [part.strip() for part in re.split(r"\s+and\s+", s) if part.strip()]
        # If someone used commas instead of 'and'
        if len(parts) == 1 and ',' in parts[0]:
            parts = [part.strip() for part in parts[0].split(',') if part.strip()]
        return parts

    def parse_annotation(self, text: str) -> str:
        lines = text.splitlines()
        url_i = 0
        while not self.re_patterns['url'].match(lines[url_i].strip()) and url_i < len(lines) - 1:
            url_i += 1

        slash_idxs = [i for i, ln in enumerate(lines[:url_i]) if ln.strip() == '\\\\']
        if not slash_idxs:
            return ''
        start_i = slash_idxs[0] + 1

        annotation_lines = [ln.strip() for ln in lines[start_i:url_i]]
        annotation = ' '.join([ln for ln in annotation_lines if ln]).strip()
        return annotation
