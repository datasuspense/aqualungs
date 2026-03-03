from omegaconf import OmegaConf

from aqualungs.download import Downloader

if __name__ == '__main__':
    config = OmegaConf.load('config.yaml')
    loader = Downloader(config)
    loader.get_messages()
    loader.batch_urls()
    loader.download_pdfs()
