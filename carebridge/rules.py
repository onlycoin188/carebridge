"""규칙 기반 위험 신호 사전 (AI 판단의 교차검증용 안전망).

AI가 놓친 위험 신호를 담당자가 놓치지 않도록, 7개 언어의 핵심 표현을 사전으로
따로 찾는다. 규칙이 찾았는데 AI가 표시하지 않은 위험은 '교차검증 경고'로 띄운다.
사전은 일부러 보수적으로(재현율 우선) 만든다. 오탐은 담당자가 한 번 보고 넘기면 되지만,
낙상·호흡곤란 같은 미탐은 비용이 크기 때문이다.
"""
from __future__ import annotations

import re

RISK_TYPES = [
    "낙상", "피부손상·욕창", "식사·수분 저하", "호흡 이상", "투약 문제",
    "인지·행동 변화", "통증", "발열·감염 의심", "정서·안전 우려", "기타",
]

# 위험 유형 -> 언어별 정규식 (대소문자 무시)
_LEX: dict[str, list[str]] = {
    "낙상": [
        r"넘어지|넘어졌|넘어짐|낙상|미끄러|주저앉|떨어지셨|떨어졌",
        r"\bng[ãa]\b|\bt[ée] ng[ãa]|tr[ượu]t ch[âa]n|b[ịi] ng[ãa]",
        r"\bjatuh|terjatuh|terpeleset|tergelincir",
        r"लड्नु|लड्नुभयो|लडे|लड्यो|चिप्लि",
        r"\bfell\b|\bfall(?:en|s)?\b|slipped|tripped|found (?:him|her|lola|lolo)?\s*on the floor",
        r"摔倒|跌倒|滑倒|摔了|跌了|坐在地上|从.{0,6}滑下",
        r"yiqil|yiqildi|sirpanib|toyib ketdi",
    ],
    "피부손상·욕창": [
        r"욕창|빨갛|붉어|발적|상처|멍(?:이|들)|짓무|물집|피부.{0,4}(?:벗겨|까졌)",
        r"v[ếe]t lo[ét]|l[ởo] lo[ét]|\bđỏ\b|b[ầa]m t[íi]m|tr[ầa]y|v[ếe]t th[ươu]ơng",
        r"\bmerah\b|\bluka\b|lecet|memar|lebam|kulit.{0,10}(?:terkelupas|melepuh)",
        r"घाउ|रातो|निलो|छाला",
        r"redness|\bred (?:spot|area|mark|patch)|(?:pressure|bed) ?sores?|\bsore (?:on|area|spot)|wound|bruis|blister|skin (?:tear|broke)",
        r"发红|红肿|伤口|褥疮|压疮|淤青|破皮|水泡",
        r"qizar|\byara\b|ko'kar|ko‘kar|teri.{0,10}shilin",
    ],
    "식사·수분 저하": [
        r"(?:식사|밥|진지|음식|물).{0,8}(?:거부|안\s?(?:드|먹|마)|못\s?(?:드|먹|마)|조금|남기|절반)|입맛이?\s?없|안\s?드셨|못\s?드셨",
        r"kh[ôo]ng (?:ch[ịi]u )?[ăa]n|b[ỏo] b[ữu]a|[ăa]n (?:r[ấa]t )?[íi]t|u[ốo]ng (?:r[ấa]t )?[íi]t (?:n[ưu][ớo]c)?|kh[ôo]ng u[ốo]ng n[ưu][ớo]c",
        r"tidak (?:mau )?makan|tidak (?:mau )?minum|makan (?:sangat )?sedikit|minum (?:sangat )?sedikit|nafsu makan (?:turun|berkurang|kurang)|makan\s?\w{0,8}\s?(?:hanya|cuma) (?:setengah|sedikit)|sisa (?:banyak|setengah)",
        r"खाना\s?खानु\s?भएन|खाना\s?खानुभएन|खानुभएन|पानी\s?(?:पिउनु\s?भएन|पिउनुभएन|कम)|भोक\s?छैन|थोरै\s?मात्र",
        r"refus\w* (?:to )?(?:eat|food|meal|lunch|dinner|breakfast|water|drink)|did(?:n'?t| not) (?:eat|drink)|not eating|ate (?:very )?little|only (?:ate|drank) (?:a little|half|a few)|ate only|no appetite|little water",
        r"不(?:肯|想)?吃|没(?:怎么)?吃|吃得(?:很)?少|喝水(?:很)?少|不(?:肯)?喝水|没胃口|剩了一半",
        r"ovqat\s?yemad|ovqat\s?yeyishdan bosh tort|suv\s?ichmad|kam\s?(?:yedi|ichdi)|ishtahasi\s?yo'q|ishtahasi\s?yo‘q",
    ],
    "호흡 이상": [
        r"숨(?:이|을|쉬기|차|가쁘)|호흡.{0,4}(?:곤란|힘들|가쁘|이상)|쌕쌕|가래.{0,4}(?:많|끓)",
        r"kh[óo] th[ởo]|th[ởo] g[ấa]p|h[ụu]t h[ơo]i|kh[òo] kh[èe]",
        r"sesak|napas (?:berat|cepat|pendek)|susah (?:bernapas|napas)|mengi",
        r"सास\s?फेर्न\s?गाह्रो|सास\s?फुल|सास\s?बढ",
        r"short(?:ness)? of breath|hard to breathe|difficulty breathing|breathing (?:fast|hard|heavy)|wheez|gasping",
        r"呼吸困难|喘不上气|气喘|喘气|气短",
        r"nafas\s?(?:qis|olish\s?qiyin)|hansira|xirillash",
    ],
    "투약 문제": [
        r"약.{0,6}(?:안\s?드|거부|뱉|못\s?드|빠뜨|잊|두\s?번|중복|안\s?먹)",
        r"kh[ôo]ng u[ốo]ng thu[ốo]c|nh[ổo] thu[ốo]c|qu[êe]n (?:cho )?u[ốo]ng thu[ốo]c|u[ốo]ng thu[ốo]c hai l[ầa]n|t[ừu] ch[ốo]i (?:u[ốo]ng )?thu[ốo]c",
        r"tidak (?:mau )?minum obat|menolak obat|memuntahkan obat|lupa (?:minum )?obat|obat.{0,10}(?:dua kali|terlewat)",
        r"औषधि\s?(?:खानु\s?भएन|खानुभएन|थुक|बिर्स|दुई\s?पटक)",
        r"(?:refus|spit|skip|miss|forgot)\w*.{0,20}(?:medicine|meds|medication|pill|tablet)|(?:medicine|meds|medication|pill)s?.{0,20}(?:refus|spit|skip|miss|twice|double)",
        r"没吃药|不(?:肯)?吃药|吐(?:出)?药|漏(?:服|吃)|忘了吃药|吃了两次药",
        r"dori(?:ni)?\s?(?:ichmad|ichishdan bosh tort|tupur|unut|ikki marta)",
    ],
    "인지·행동 변화": [
        r"평소(?:와|랑)\s?다르|혼란|헛것|횡설수설|못\s?알아보|길을?\s?잃|배회|섬망|갑자기.{0,6}(?:화|소리|공격)|말이\s?어눌",
        r"l[úu] l[ẫa]n|kh[ôo]ng nh[ậa]n ra|n[óo]i l[ảa]m nh[ảa]m|kh[áa]c th[ưu][ờo]ng|đi lang thang|ho[ảa]ng lo[ạa]n",
        r"bingung|linglung|tidak mengenali|bicara (?:ngawur|melantur|cadel)|berbeda dari biasanya|keluyuran",
        r"अलमल|चिन्नु\s?भएन|नचिन|बरबरा|सामान्य\s?भन्दा\s?फरक",
        r"confus|disorient|didn'?t recognize|not recogni[sz]|talking nonsense|not (?:her|him)self|wander|agitat|slurred",
        r"糊涂|认不出|胡言乱语|和平时不一样|迷路|徘徊|躁动|说话含糊",
        r"chalkash|tanimad|odatdagidan\s?boshqacha|adashib|bezovta",
    ],
    "통증": [
        r"아프|아파|통증|쑤시|저리",
        r"\bđau\b|nh[ứu]c",
        r"\bsakit\b|nyeri|ngilu",
        r"दुख्|दुखाइ|पीडा",
        r"\bpain\b|hurts?\b|aching|\bache\b|sore (?:knee|back|leg|arm)",
        r"疼|痛",
        r"og'ri|og‘ri|\bdard\b",
    ],
    "발열·감염 의심": [
        r"열이|발열|미열|고열|오한|기침|설사|구토|소변.{0,6}(?:냄새|탁|색)",
        r"\bsốt\b|\bho (?:nhi[ềe]u|li[êe]n t[ụu]c|c[óo] đờm)|ti[êe]u ch[ảa]y|\bnôn\b|n[ưu][ớo]c ti[ểe]u.{0,10}(?:h[ôo]i|đ[ụu]c)",
        r"demam|panas tinggi|batuk|diare|muntah|menggigil|urin.{0,10}(?:bau|keruh)",
        r"ज्वरो|खोकी|पखाला|बान्ता",
        r"fever|temperature (?:high|of 3[89])|chills|cough|diarrh|vomit|urine.{0,15}(?:smell|cloudy)",
        r"发烧|发热|咳嗽|腹泻|呕吐|发冷|尿.{0,4}(?:臭|浑浊)",
        r"isitma|harorat|yo'tal|yo‘tal|ich\s?ketish|qusish",
    ],
    "정서·안전 우려": [
        r"울(?:었|고|면서)|우셨|죽고\s?싶|불안|무서워|맞았|때렸|학대|방치|외롭",
        r"kh[óo]c|mu[ốo]n ch[ếe]t|s[ợo] h[ãa]i|lo l[ắa]ng|b[ịi] đ[áa]nh",
        r"menangis|ingin mati|takut|cemas|dipukul",
        r"रुनु|रोए|मर्न\s?मन|डर|पिट",
        r"cried|crying|want(?:s|ed)? to die|scared|afraid|anxious|hit (?:her|him)|lonely",
        r"哭|想死|害怕|焦虑|被打",
        r"yig'la|yig‘la|o'lgim|o‘lgim|qo'rq|qo‘rq|xavotir",
    ],
}

_COMPILED = {k: [re.compile(p, re.IGNORECASE) for p in v] for k, v in _LEX.items()}

# 위험 유형별 기본 긴급도 (규칙만으로 판정할 때)
DEFAULT_LEVEL = {
    "낙상": "긴급", "호흡 이상": "긴급", "투약 문제": "주의", "피부손상·욕창": "주의",
    "식사·수분 저하": "주의", "인지·행동 변화": "주의", "발열·감염 의심": "주의",
    "정서·안전 우려": "주의", "통증": "관찰", "기타": "관찰",
}


def scan(text: str) -> list[dict]:
    """원문에서 위험 표현을 찾는다. [{type, match, start, end}]"""
    hits: list[dict] = []
    for rtype, pats in _COMPILED.items():
        for p in pats:
            m = p.search(text)
            if m:
                hits.append({"type": rtype, "match": m.group(0), "start": m.start(), "end": m.end()})
                break
    return hits


LANG_NAMES = {
    "ko": "한국어", "vi": "베트남어", "id": "인도네시아어", "ne": "네팔어", "en": "영어",
    "tl": "필리핀어(타갈로그)", "zh": "중국어", "uz": "우즈베크어", "th": "태국어",
    "km": "크메르어", "mn": "몽골어", "my": "미얀마어", "ru": "러시아어", "other": "기타",
}


def guess_language(text: str) -> str:
    """간단한 문자·어휘 기반 언어 추정 (AI 결과 검증·데모 모드용)."""
    if re.search(r"[ऀ-ॿ]", text):
        return "ne"
    if re.search(r"[฀-๿]", text):
        return "th"
    if re.search(r"[ក-៿]", text):
        return "km"
    if re.search(r"[က-႟]", text):
        return "my"
    hangul = len(re.findall(r"[가-힣]", text))
    han = len(re.findall(r"[一-鿿]", text))
    cyr = len(re.findall(r"[Ѐ-ӿ]", text))
    latin = len(re.findall(r"[A-Za-zÀ-ỹ]", text))
    if han > hangul and han > 5:
        return "zh"
    if cyr > latin and cyr > 5:
        return "mn" if re.search(r"[өүӨҮ]", text) else "ru"
    if hangul >= latin:
        return "ko"
    low = text.lower()
    if re.search(r"[ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]", low):
        return "vi"
    scores = {
        "id": len(re.findall(r"\b(?:dan|tidak|yang|sudah|makan|ibu|nenek|kakek|sedikit|pagi|siang|malam|mau)\b", low)),
        "uz": len(re.findall(r"\b(?:va|bilan|emas|bugun|kechasi|ertalab|buvi|bobo|ovqat|juda)\b|o'|g'|o‘|g‘", low)),
        "tl": len(re.findall(r"\b(?:ang|ng|mga|siya|hindi|kumain|po|kanina|lola|lolo|sa)\b", low)),
        "en": len(re.findall(r"\b(?:the|and|she|he|was|did|not|her|his|after|today|morning)\b", low)),
    }
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "other"
    # 타갈로그·영어 혼용(Taglish)은 영어로 분류 비중이 크면 en
    if best == "tl" and scores["en"] >= scores["tl"]:
        return "en"
    return best
