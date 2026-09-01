# -*- coding: utf-8 -*-
"""地理数据映射表：国家码/城市/Cloudflare 机房码 → 中文"""


def flag(cc):
    """ISO 3166-1 两位码 → 国旗 emoji。
    用区域指示符（Regional Indicator）拼接，A→🇦 ... Z→🇿，两个字母组合即国旗。
    这样任何国家都自动有旗，不用维护映射表；码非法时返回空串由调用方兜底。"""
    cc = (cc or '').strip().upper()
    if len(cc) != 2 or not cc.isascii() or not cc.isalpha():
        return ''
    return ''.join(chr(0x1F1E6 + ord(c) - ord('A')) for c in cc)


# ISO 3166 国家/地区码 → 中文名
COUNTRY_ZH = {
    'CR': '哥斯达黎加', 'DO': '多米尼加', 'EC': '厄瓜多尔', 'JM': '牙买加',
    'RE': '留尼汪', 'YT': '马约特', 'PA': '巴拿马', 'GT': '危地马拉',
    'UY': '乌拉圭', 'PY': '巴拉圭', 'BO': '玻利维亚', 'VE': '委内瑞拉',
    'CU': '古巴', 'PR': '波多黎各', 'TT': '特立尼达和多巴哥', 'BS': '巴哈马',
    'GH': '加纳', 'TZ': '坦桑尼亚', 'UG': '乌干达', 'ET': '埃塞俄比亚',
    'DZ': '阿尔及利亚', 'TN': '突尼斯', 'SN': '塞内加尔', 'CI': '科特迪瓦',
    'ZW': '津巴布韦', 'ZM': '赞比亚', 'AO': '安哥拉', 'MZ': '莫桑比克',
    'LB': '黎巴嫩', 'SY': '叙利亚', 'YE': '也门', 'AF': '阿富汗',
    'MV': '马尔代夫', 'BT': '不丹', 'TJ': '塔吉克斯坦', 'TM': '土库曼斯坦',
    'ME': '黑山', 'XK': '科索沃', 'LI': '列支敦士登', 'AD': '安道尔',
    'MC': '摩纳哥', 'SM': '圣马力诺', 'FO': '法罗群岛', 'GI': '直布罗陀',
    'FJ': '斐济', 'PG': '巴布亚新几内亚', 'NC': '新喀里多尼亚', 'GU': '关岛',
    'SC': '塞舌尔', 'MU': '毛里求斯', 'MT': '马耳他', 'CY': '塞浦路斯',
    'CN': '中国', 'HK': '香港', 'MO': '澳门', 'TW': '台湾',
    'JP': '日本', 'KR': '韩国', 'KP': '朝鲜', 'MN': '蒙古',
    'SG': '新加坡', 'MY': '马来西亚', 'TH': '泰国', 'VN': '越南',
    'PH': '菲律宾', 'ID': '印度尼西亚', 'KH': '柬埔寨', 'LA': '老挝',
    'MM': '缅甸', 'BN': '文莱', 'IN': '印度', 'PK': '巴基斯坦',
    'BD': '孟加拉国', 'LK': '斯里兰卡', 'NP': '尼泊尔', 'KZ': '哈萨克斯坦',
    'UZ': '乌兹别克斯坦', 'KG': '吉尔吉斯斯坦', 'TR': '土耳其', 'AE': '阿联酋',
    'SA': '沙特阿拉伯', 'QA': '卡塔尔', 'KW': '科威特', 'BH': '巴林',
    'OM': '阿曼', 'IL': '以色列', 'JO': '约旦', 'IR': '伊朗', 'IQ': '伊拉克',
    'GE': '格鲁吉亚', 'AM': '亚美尼亚', 'AZ': '阿塞拜疆',
    'US': '美国', 'CA': '加拿大', 'MX': '墨西哥',
    'BR': '巴西', 'AR': '阿根廷', 'CL': '智利', 'CO': '哥伦比亚', 'PE': '秘鲁',
    'GB': '英国', 'DE': '德国', 'FR': '法国', 'IT': '意大利', 'ES': '西班牙',
    'PT': '葡萄牙', 'NL': '荷兰', 'BE': '比利时', 'LU': '卢森堡', 'IE': '爱尔兰',
    'CH': '瑞士', 'AT': '奥地利', 'PL': '波兰', 'CZ': '捷克', 'SK': '斯洛伐克',
    'HU': '匈牙利', 'RO': '罗马尼亚', 'BG': '保加利亚', 'GR': '希腊',
    'SE': '瑞典', 'NO': '挪威', 'FI': '芬兰', 'DK': '丹麦', 'IS': '冰岛',
    'EE': '爱沙尼亚', 'LV': '拉脱维亚', 'LT': '立陶宛',
    'RU': '俄罗斯', 'UA': '乌克兰', 'BY': '白俄罗斯', 'MD': '摩尔多瓦',
    'RS': '塞尔维亚', 'HR': '克罗地亚', 'SI': '斯洛文尼亚', 'BA': '波黑',
    'MK': '北马其顿', 'AL': '阿尔巴尼亚', 'CY': '塞浦路斯', 'MT': '马耳他',
    'AU': '澳大利亚', 'NZ': '新西兰',
    'EG': '埃及', 'ZA': '南非', 'NG': '尼日利亚', 'KE': '肯尼亚', 'MA': '摩洛哥',
}

# 大洲划分（用于接入点与投票结果的矛盾判定）
_CONT = {
    'AS': ['CN','HK','MO','TW','JP','KR','KP','MN','SG','MY','TH','VN','PH','ID','KH','LA','MM','BN',
           'IN','PK','BD','LK','NP','KZ','UZ','KG','TR','AE','SA','QA','KW','BH','OM','IL','JO','IR','IQ',
           'GE','AM','AZ'],
    'EU': ['GB','DE','FR','IT','ES','PT','NL','BE','LU','IE','CH','AT','PL','CZ','SK','HU','RO','BG','GR',
           'SE','NO','FI','DK','IS','EE','LV','LT','RU','UA','BY','MD','RS','HR','SI','BA','MK','AL','CY','MT'],
    'NA': ['US','CA','MX'],
    'SA': ['BR','AR','CL','CO','PE'],
    'OC': ['AU','NZ'],
    'AF': ['EG','ZA','NG','KE','MA'],
}
CONTINENT = {cc: cont for cont, ccs in _CONT.items() for cc in ccs}

# 城邦型地区：城市直接使用地区名
CITY_STATE = {'HK': '香港', 'MO': '澳门', 'SG': '新加坡'}

# 常见城市英文名（小写）→ 中文
CITY_ZH = {
    'Yokohama': '横滨',
    'Toyokawa': '丰川',
    'Pyeongtaek': '平泽',
    'Chuncheon': '春川',
    'tokyo': '东京', 'osaka': '大阪', 'nagoya': '名古屋', 'fukuoka': '福冈', 'sapporo': '札幌',
    'seoul': '首尔', 'busan': '釜山', 'incheon': '仁川',
    'taipei': '台北', 'new taipei': '新北', 'taichung': '台中', 'kaohsiung': '高雄', 'taoyuan': '桃园',
    'hong kong': '香港', 'macau': '澳门', 'singapore': '新加坡',
    'bangkok': '曼谷', 'hanoi': '河内', 'ho chi minh city': '胡志明市', 'kuala lumpur': '吉隆坡',
    'jakarta': '雅加达', 'manila': '马尼拉', 'phnom penh': '金边',
    'mumbai': '孟买', 'delhi': '新德里', 'new delhi': '新德里', 'chennai': '金奈', 'bangalore': '班加罗尔',
    'dubai': '迪拜', 'abu dhabi': '阿布扎比', 'istanbul': '伊斯坦布尔', 'tel aviv': '特拉维夫',
    'riyadh': '利雅得', 'doha': '多哈', 'almaty': '阿拉木图', 'tashkent': '塔什干',
    'los angeles': '洛杉矶', 'san jose': '圣何塞', 'san francisco': '旧金山', 'seattle': '西雅图',
    'new york': '纽约', 'new york city': '纽约', 'ashburn': '阿什本', 'washington': '华盛顿',
    'chicago': '芝加哥', 'dallas': '达拉斯', 'miami': '迈阿密', 'atlanta': '亚特兰大',
    'phoenix': '凤凰城', 'las vegas': '拉斯维加斯', 'salt lake city': '盐湖城', 'denver': '丹佛',
    'houston': '休斯敦', 'boston': '波士顿', 'portland': '波特兰', 'buffalo': '布法罗',
    'santa clara': '圣克拉拉', 'fremont': '弗里蒙特', 'piscataway': '皮斯卡特维', 'secaucus': '锡考克斯',
    'toronto': '多伦多', 'vancouver': '温哥华', 'montreal': '蒙特利尔',
    'mexico city': '墨西哥城', 'sao paulo': '圣保罗', 'buenos aires': '布宜诺斯艾利斯', 'santiago': '圣地亚哥',
    'london': '伦敦', 'manchester': '曼彻斯特', 'coventry': '考文垂', 'edinburgh': '爱丁堡',
    'frankfurt': '法兰克福', 'frankfurt am main': '法兰克福', 'berlin': '柏林', 'munich': '慕尼黑',
    'dusseldorf': '杜塞尔多夫', 'düsseldorf': '杜塞尔多夫', 'hamburg': '汉堡', 'nuremberg': '纽伦堡',
    'falkenstein': '法尔肯施泰因', 'limburg': '林堡', 'limburg an der lahn': '林堡',
    'paris': '巴黎', 'marseille': '马赛', 'strasbourg': '斯特拉斯堡', 'roubaix': '鲁贝', 'gravelines': '格拉沃利讷',
    'amsterdam': '阿姆斯特丹', 'rotterdam': '鹿特丹', 'the hague': '海牙', 'naaldwijk': '纳尔德韦克',
    'brussels': '布鲁塞尔', 'luxembourg': '卢森堡', 'dublin': '都柏林',
    'zurich': '苏黎世', 'geneva': '日内瓦', 'vienna': '维也纳', 'salzburg': '萨尔茨堡',
    'warsaw': '华沙', 'krakow': '克拉科夫', 'gdansk': '格但斯克', 'poznan': '波兹南',
    'prague': '布拉格', 'brno': '布尔诺', 'bratislava': '布拉迪斯拉发', 'budapest': '布达佩斯',
    'bucharest': '布加勒斯特', 'sofia': '索菲亚', 'athens': '雅典', 'belgrade': '贝尔格莱德',
    'madrid': '马德里', 'barcelona': '巴塞罗那', 'lisbon': '里斯本', 'milan': '米兰', 'rome': '罗马',
    'stockholm': '斯德哥尔摩', 'oslo': '奥斯陆', 'helsinki': '赫尔辛基', 'copenhagen': '哥本哈根',
    'reykjavik': '雷克雅未克', 'tallinn': '塔林', 'riga': '里加', 'vilnius': '维尔纽斯',
    'moscow': '莫斯科', 'saint petersburg': '圣彼得堡', 'st petersburg': '圣彼得堡',
    'novosibirsk': '新西伯利亚', 'yekaterinburg': '叶卡捷琳堡', 'khabarovsk': '哈巴罗夫斯克',
    'kyiv': '基辅', 'kiev': '基辅', 'minsk': '明斯克', 'chisinau': '基希讷乌',
    'sydney': '悉尼', 'melbourne': '墨尔本', 'brisbane': '布里斯班', 'perth': '珀斯', 'auckland': '奥克兰',
    'cairo': '开罗', 'johannesburg': '约翰内斯堡', 'lagos': '拉各斯', 'nairobi': '内罗毕',
}

# Cloudflare 机房码（IATA）→ (城市中文, 国家码)
COLO = {
    'NRT': ('东京', 'JP'), 'HND': ('东京', 'JP'), 'KIX': ('大阪', 'JP'), 'FUK': ('福冈', 'JP'), 'OKA': ('那霸', 'JP'),
    'ICN': ('首尔', 'KR'), 'PUS': ('釜山', 'KR'),
    'HKG': ('香港', 'HK'), 'MFM': ('澳门', 'MO'), 'TPE': ('台北', 'TW'), 'KHH': ('高雄', 'TW'),
    'SIN': ('新加坡', 'SG'), 'KUL': ('吉隆坡', 'MY'), 'BKK': ('曼谷', 'TH'),
    'HAN': ('河内', 'VN'), 'SGN': ('胡志明市', 'VN'), 'MNL': ('马尼拉', 'PH'),
    'CGK': ('雅加达', 'ID'), 'PNH': ('金边', 'KH'),
    'BOM': ('孟买', 'IN'), 'DEL': ('新德里', 'IN'), 'MAA': ('金奈', 'IN'), 'BLR': ('班加罗尔', 'IN'),
    'DXB': ('迪拜', 'AE'), 'AUH': ('阿布扎比', 'AE'), 'IST': ('伊斯坦布尔', 'TR'), 'TLV': ('特拉维夫', 'IL'),
    'RUH': ('利雅得', 'SA'), 'DOH': ('多哈', 'QA'), 'ALA': ('阿拉木图', 'KZ'), 'TAS': ('塔什干', 'UZ'),
    'LAX': ('洛杉矶', 'US'), 'SJC': ('圣何塞', 'US'), 'SFO': ('旧金山', 'US'), 'SEA': ('西雅图', 'US'),
    'EWR': ('纽瓦克', 'US'), 'JFK': ('纽约', 'US'), 'IAD': ('阿什本', 'US'), 'ORD': ('芝加哥', 'US'),
    'DFW': ('达拉斯', 'US'), 'MIA': ('迈阿密', 'US'), 'ATL': ('亚特兰大', 'US'), 'PHX': ('凤凰城', 'US'),
    'LAS': ('拉斯维加斯', 'US'), 'SLC': ('盐湖城', 'US'), 'DEN': ('丹佛', 'US'), 'IAH': ('休斯敦', 'US'),
    'BOS': ('波士顿', 'US'), 'PDX': ('波特兰', 'US'), 'BUF': ('布法罗', 'US'),
    'YYZ': ('多伦多', 'CA'), 'YVR': ('温哥华', 'CA'), 'YUL': ('蒙特利尔', 'CA'),
    'MEX': ('墨西哥城', 'MX'), 'GRU': ('圣保罗', 'BR'), 'EZE': ('布宜诺斯艾利斯', 'AR'), 'SCL': ('圣地亚哥', 'CL'),
    'LHR': ('伦敦', 'GB'), 'MAN': ('曼彻斯特', 'GB'), 'EDI': ('爱丁堡', 'GB'),
    'FRA': ('法兰克福', 'DE'), 'MUC': ('慕尼黑', 'DE'), 'DUS': ('杜塞尔多夫', 'DE'),
    'HAM': ('汉堡', 'DE'), 'TXL': ('柏林', 'DE'), 'BER': ('柏林', 'DE'),
    'CDG': ('巴黎', 'FR'), 'MRS': ('马赛', 'FR'), 'AMS': ('阿姆斯特丹', 'NL'), 'BRU': ('布鲁塞尔', 'BE'),
    'LUX': ('卢森堡', 'LU'), 'DUB': ('都柏林', 'IE'), 'ZRH': ('苏黎世', 'CH'), 'GVA': ('日内瓦', 'CH'),
    'VIE': ('维也纳', 'AT'), 'WAW': ('华沙', 'PL'), 'KRK': ('克拉科夫', 'PL'), 'GDN': ('格但斯克', 'PL'),
    'PRG': ('布拉格', 'CZ'), 'BTS': ('布拉迪斯拉发', 'SK'), 'BUD': ('布达佩斯', 'HU'),
    'OTP': ('布加勒斯特', 'RO'), 'SOF': ('索菲亚', 'BG'), 'ATH': ('雅典', 'GR'), 'BEG': ('贝尔格莱德', 'RS'),
    'MAD': ('马德里', 'ES'), 'BCN': ('巴塞罗那', 'ES'), 'LIS': ('里斯本', 'PT'),
    'MXP': ('米兰', 'IT'), 'FCO': ('罗马', 'IT'),
    'ARN': ('斯德哥尔摩', 'SE'), 'OSL': ('奥斯陆', 'NO'), 'HEL': ('赫尔辛基', 'FI'), 'CPH': ('哥本哈根', 'DK'),
    'KEF': ('雷克雅未克', 'IS'), 'TLL': ('塔林', 'EE'), 'RIX': ('里加', 'LV'), 'VNO': ('维尔纽斯', 'LT'),
    'DME': ('莫斯科', 'RU'), 'SVO': ('莫斯科', 'RU'), 'LED': ('圣彼得堡', 'RU'), 'KJA': ('克拉斯诺亚尔斯克', 'RU'),
    'KBP': ('基辅', 'UA'), 'MSQ': ('明斯克', 'BY'), 'KIV': ('基希讷乌', 'MD'),
    'SYD': ('悉尼', 'AU'), 'MEL': ('墨尔本', 'AU'), 'BNE': ('布里斯班', 'AU'), 'PER': ('珀斯', 'AU'),
    'AKL': ('奥克兰', 'NZ'),
    'CAI': ('开罗', 'EG'), 'JNB': ('约翰内斯堡', 'ZA'), 'LOS': ('拉各斯', 'NG'), 'NBO': ('内罗毕', 'KE'),
}

# 延迟仲裁锚点：DataPacket 各城市测速端点（单播、分城市）。
# 端点可用性会变化（实测曾遇 waw 失效），仲裁脚本运行时逐个验证、不通自动跳过；
# 若某大洲锚点全部失效，可换用其他单播分城市的测速站点替换本表。
ANCHORS = {
    'EU': {
        'FRA法兰克福': 'fra.download.datapacket.com',
        'AMS阿姆斯特丹': 'ams.download.datapacket.com',
        'LON伦敦': 'lon.download.datapacket.com',
        'PAR巴黎': 'par.download.datapacket.com',
        'PRG布拉格': 'prg.download.datapacket.com',
        'VIE维也纳': 'vie.download.datapacket.com',
        'WAW华沙': 'waw.download.datapacket.com',
        'STO斯德哥尔摩': 'sto.download.datapacket.com',
        'MAD马德里': 'mad.download.datapacket.com',
        'MIL米兰': 'mil.download.datapacket.com',
    },
    'NA': {
        'NYC纽约': 'nyc.download.datapacket.com',
        'CHI芝加哥': 'chi.download.datapacket.com',
        'DAL达拉斯': 'dal.download.datapacket.com',
        'LAX洛杉矶': 'lax.download.datapacket.com',
        'MIA迈阿密': 'mia.download.datapacket.com',
    },
    'AS': {
        'SGP新加坡': 'sgp.download.datapacket.com',
        'HKG香港': 'hkg.download.datapacket.com',
        'TYO东京': 'tyo.download.datapacket.com',
    },
}


# 地区展示顺序：按使用习惯从近到远排列（亚太 → 北美 → 欧洲 → 其他）。
# 未列出的已知地区排在列表之后，未识别地区永远垫底。
REGION_ORDER = [
    'HK', 'TW', 'MO', 'JP', 'KR', 'SG',
    'MY', 'TH', 'VN', 'PH', 'ID', 'KH', 'LA', 'MM', 'BN',
    'IN', 'PK', 'BD', 'LK', 'NP', 'KZ', 'UZ', 'KG',
    'TR', 'AE', 'SA', 'QA', 'KW', 'BH', 'OM', 'IL', 'JO', 'IR', 'IQ',
    'GE', 'AM', 'AZ',
    'US', 'CA', 'MX',
    'GB', 'IE', 'DE', 'NL', 'BE', 'LU', 'FR', 'CH', 'AT',
    'ES', 'PT', 'IT', 'GR', 'MT', 'CY',
    'SE', 'NO', 'FI', 'DK', 'IS', 'EE', 'LV', 'LT',
    'PL', 'CZ', 'SK', 'HU', 'RO', 'BG', 'RS', 'HR', 'SI', 'BA', 'MK', 'AL',
    'RU', 'UA', 'BY', 'MD',
    'AU', 'NZ',
    'BR', 'AR', 'CL', 'CO', 'PE', 'UY', 'PY', 'BO', 'VE', 'EC',
    'CR', 'PA', 'GT', 'DO', 'JM', 'CU', 'PR', 'TT', 'BS',
    'ZA', 'EG', 'NG', 'KE', 'MA', 'SC', 'MU', 'GH', 'TZ', 'UG', 'ET',
    'DZ', 'TN', 'SN', 'CI', 'ZW', 'ZM', 'AO', 'MZ', 'RE', 'YT',
    'CN',
]
_RANK = {cc: i for i, cc in enumerate(REGION_ORDER)}


def region_rank(cc):
    """地区排序权重：越小越靠前。未列出的已知地区居中，未识别地区垫底。"""
    if not cc:
        return 9999
    return _RANK.get(cc.upper(), 900)


# 行政区划尾缀：让「首尔特别市」「达卡专区」「北荷兰省」回到常用地名。
# 先长后短匹配，整个名字就是尾缀时不动（如「京都」不该被剪成「京」）。
ADMIN_SUFFIXES = ('特别行政区', '特别市', '广域市', '直辖市', '自治州', '自治区',
                  '首都大区', '大都会', '专区', '大区', '地区',
                  '縣', '邦', '省', '州', '市', '县', '都', '府', '區', '区')


def trim_admin(name):
    """去掉中文地名的行政区划尾缀；英文与过短的名字原样返回。"""
    n = (name or '').strip()
    for suf in ADMIN_SUFFIXES:
        if len(n) > len(suf) + 1 and n.endswith(suf):
            return n[:-len(suf)]
    return n


# 城市所属地区的纠正表：订阅方常把这些城市错标成所在国的邻国/宗主国
CITY_REGION_FIX = {'台北': 'TW', '新北': 'TW', '台中': 'TW', '台南': 'TW',
                   '高雄': 'TW', '桃园': 'TW', '基隆': 'TW', '新竹': 'TW',
                   '香港': 'HK', '澳门': 'MO'}
