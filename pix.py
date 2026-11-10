from binascii import crc_hqx
from unicodedata import normalize


def pix_text(value, limit):
    return normalize('NFKD', value).encode('ascii', 'ignore').decode().upper()[:limit].strip()


def pix_payload(key, name, city, amount, txid):
    def field(tag, value):
        return f'{tag}{len(value.encode("utf-8")):02d}{value}'

    account = field('00', 'br.gov.bcb.pix') + field('01', key)
    payload = (
        field('00', '01') + field('26', account) + field('52', '0000')
        + field('53', '986') + field('54', f'{amount:.2f}') + field('58', 'BR')
        + field('59', name) + field('60', city) + field('62', field('05', txid)) + '6304'
    )
    return payload + f'{crc_hqx(payload.encode("utf-8"), 0xffff):04X}'
