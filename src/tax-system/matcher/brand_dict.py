"""
matcher/brand_dict.py — 日英品牌对照表

用于 Layer 2 品牌词典模糊匹配
将日文品牌名映射到英文别名列表
"""

# 品牌对照表：日文 → [英文别名 1, 英文别名 2, ...]
BRAND_DICT = {
    # 玩具/模型厂商
    "バンダイ": ["Bandai", "BANDAI"],
    "タカラトミー": ["Takara Tomy", "TAKARA TOMY", "Tomy"],
    "セガ": ["Sega", "SEGA"],
    "カプコン": ["Capcom", "CAPCOM"],
    "スクウェア・エニックス": ["Square Enix", "SQUARE ENIX"],
    "任天堂": ["Nintendo", "NINTENDO"],
    "ソニー": ["Sony", "SONY"],
    "コナミ": ["Konami", "KONAMI"],
    "ナムコ": ["Namco", "NAMCO"],
    "ハドソン": ["Hudson", "HUDSON"],
    "コーエー": ["Koei", "KOEI", "Tecmo", "TECMO"],
    "フロム・ソフトウェア": ["FromSoftware", "FROM SOFTWARE"],
    "アトラス": ["Atlus", "ATLUS"],
    "日本ファルコム": ["Nihon Falcom", "Falcom", "FALCOM"],
    "コーエーテクモ": ["Koei Tecmo", "KOEI TECMO"],
    
    # 动漫/游戏角色
    "ワンピース": ["One Piece", "ONE PIECE"],
    "ナルト": ["Naruto", "NARUTO"],
    "ドラゴンボール": ["Dragon Ball", "DRAGON BALL"],
    "ポケットモンスター": ["Pokemon", "Pokémon", "POKEMON"],
    "遊戯王": ["Yu-Gi-Oh", "YU-GI-OH"],
    "ガンダム": ["Gundam", "GUNDAM"],
    "エヴァンゲリオン": ["Evangelion", "EVANGELION"],
    "ドラえもん": ["Doraemon", "DORAEMON"],
    "ハローキティ": ["Hello Kitty", "HELLO KITTY", "Sanrio"],
    "ディズニー": ["Disney", "DISNEY"],
    "スタジオジブリ": ["Studio Ghibli", "GHIBLI"],
    
    # 其他常见品牌
    "トミーテック": ["Tomytec", "TOMYTEC"],
    "海洋堂": ["Kaiyodo", "KAIYODO"],
    "グッドスマイルカンパニー": ["Good Smile Company", "GSC", "GoodSmile"],
    "マックスファクトリー": ["Max Factory", "MAX FACTORY"],
    "フリュー": ["Furyu", "FURYU"],
    "バンプレスト": ["Banpresto", "BANPRESTO"],
    "メガハウス": ["MegaHouse", "MEGAHOUSE"],
    "アルター": ["Alter", "ALTER"],
    "コトブキヤ": ["Kotobukiya", "KOTOBUKIYA"],
    "寿屋": ["Kotobukiya", "KOTOBUKIYA"],
}

# 反向索引：英文 → 日文
BRAND_DICT_REVERSE = {}
for jp, ens in BRAND_DICT.items():
    for en in ens:
        if en not in BRAND_DICT_REVERSE:
            BRAND_DICT_REVERSE[en] = []
        BRAND_DICT_REVERSE[en].append(jp)


def normalize_brand(brand_jp: str) -> list[str]:
    """
    将日文品牌名转换为英文别名列表
    
    参数:
        brand_jp: 日文品牌名
    
    返回:
        英文别名列表（如果没有匹配，返回原日文）
    """
    return BRAND_DICT.get(brand_jp, [brand_jp])


def normalize_brand_en(brand_en: str) -> list[str]:
    """
    将英文品牌名转换为日文 + 其他英文别名列表
    
    参数:
        brand_en: 英文品牌名
    
    返回:
        日文 + 英文别名列表（如果没有匹配，返回原英文）
    """
    return BRAND_DICT_REVERSE.get(brand_en, [brand_en])


def extract_brand_from_text(text: str) -> str | None:
    """
    从商品文本中提取品牌名
    
    参数:
        text: 商品标题或描述
    
    返回:
        品牌名（日文或英文），如果没有找到返回 None
    """
    if not text:
        return None
    
    text_upper = text.upper()
    
    # 检查日文品牌
    for jp_brand in BRAND_DICT.keys():
        if jp_brand in text:
            return jp_brand
    
    # 检查英文品牌
    for en_brand in BRAND_DICT_REVERSE.keys():
        if en_brand.upper() in text_upper:
            return en_brand
    
    return None


def brand_match(text1: str, text2: str) -> bool:
    """
    检查两个文本是否包含相同的品牌
    
    参数:
        text1: 文本 1（如采购商品名）
        text2: 文本 2（如 eBay 订单标题）
    
    返回:
        True 如果包含相同品牌
    """
    brand1 = extract_brand_from_text(text1)
    brand2 = extract_brand_from_text(text2)
    
    if brand1 is None or brand2 is None:
        return False
    
    # 标准化后比较
    brand1_list = set(normalize_brand(brand1) if brand1 in BRAND_DICT else BRAND_DICT_REVERSE.get(brand1.upper(), [brand1]))
    brand2_list = set(normalize_brand(brand2) if brand2 in BRAND_DICT else BRAND_DICT_REVERSE.get(brand2.upper(), [brand2]))
    
    return bool(brand1_list & brand2_list)
