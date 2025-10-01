from sites.myhome.parse_card import parse_card as parse_myhome
# from sites.ss.parse_card import parse_card as parse_ss  # подключим позже

def get_parse_function(url: str):
    if "myhome.ge" in url:
        return parse_myhome
    # elif "ss.ge" in url:
    #     return parse_ss
    else:
        raise ValueError(f"Нет обработчика parse_card для URL: {url}")