IDX_STOCKS = {
    "Banking": [
        "BBCA", "BBRI", "BMRI", "BBNI", "BRIS", "BNGA", "BTPS", "NISP",
        "BDMN", "BNII", "PNBN", "BJTM", "BJBR", "MEGA", "AGRO", "ARTO",
    ],
    "Technology": [
        "TLKM", "EMTK", "BUKA", "GOTO", "DMMX", "MCAS", "KIOS", "MTDL",
        "MLPT", "LUCK", "DCII", "ISAT", "EXCL",
    ],
    "Energy": [
        "ADRO", "PTBA", "ITMG", "HRUM", "BYAN", "MYOH", "GEMS", "DEWA",
        "MDKA", "ANTM", "INCO", "MEDC", "ELSA", "AKRA", "PGAS",
    ],
    "Consumer": [
        "UNVR", "ICBP", "INDF", "MYOR", "SIDO", "GGRM", "HMSP", "ROTI",
        "CLEO", "GOOD", "HOKI", "ULTJ", "DLTA", "MLBI",
    ],
    "Healthcare": [
        "KLBF", "SIDO", "MIKA", "HEAL", "DGNS", "PRDA", "PYFA", "TSPC",
        "KAEF", "INAF", "SOHO",
    ],
    "Property": [
        "BSDE", "SMRA", "CTRA", "PWON", "LPKR", "MDLN", "DILD", "PANI",
        "APLN", "BKSL", "JRPT", "KIJA",
    ],
    "Industrial": [
        "ASII", "AUTO", "SMSM", "IMAS", "GJTL", "INDS", "BRAM", "PRAS",
        "INCI", "ETWA", "CPIN", "JPFA", "MAIN",
    ],
    "Infrastructure": [
        "JSMR", "WIKA", "PTPP", "ADHI", "WSKT", "TBIG", "TOWR",
        "KOPI", "META",
    ],
    "Finance": [
        "BBTN", "ADMF", "BFI", "CFIN", "MFIN", "VRNA", "APIC",
        "WOMF", "BPFI",
    ],
    "Plantation": [
        "AALI", "LSIP", "SIMP", "SSMS", "SGRO", "PALM", "DSNG", "TAPG",
    ],
    "Mining": [
        "TINS", "PTBA", "ANTM", "INCO", "PSAB", "ARCI", "SMMT",
    ],
    "Retail": [
        "AMRT", "MIDI", "HERO", "LPPF", "MAPI", "ACES", "RALS", "CSAP",
    ],
}

ALL_IDX_STOCKS = []
for sector, stocks in IDX_STOCKS.items():
    for s in stocks:
        if s not in ALL_IDX_STOCKS:
            ALL_IDX_STOCKS.append(s)

FOCUS_BROKERS = ["AK", "BK", "YP", "CC", "PD", "XL", "MG", "ZP", "RX", "OD"]

SECTOR_ETFS = {
    "Banking":       "BBCA.JK",
    "Technology":    "TLKM.JK",
    "Energy":        "ADRO.JK",
    "Consumer":      "UNVR.JK",
    "Healthcare":    "KLBF.JK",
    "Property":      "BSDE.JK",
    "Industrial":    "ASII.JK",
    "Infrastructure":"JSMR.JK",
    "Finance":       "BBTN.JK",
    "Plantation":    "AALI.JK",
}

IHSG_TICKER = "^JKSE"

SCREENER_NAMES = {
    "ara_hunter":       "🎯 ARA HUNTER",
    "bsjp":             "📈 BSJP",
    "big_accumulation": "🏦 BIG ACCUMULATION",
    "scalper_pro":      "⚡ SCALPER PRO",
}

MIN_VALUE_ARA = 5_000_000_000
MIN_VALUE_BSJP = 10_000_000_000
MIN_VALUE_BIG = 3_000_000_000

# Persistent bottom keyboard button labels
BTN_SCREENER  = "📈 Screener"
BTN_HEATMAP   = "🔥 Heatmap"
BTN_SECTOR    = "🔄 Sector"
BTN_BANDAR    = "🏦 Bandar"
BTN_WATCHLIST = "📊 Watchlist"
BTN_MOMENTUM  = "⚡ Momentum"
BTN_FOREIGN   = "💰 Foreign Flow"
BTN_BREADTH   = "📉 Breadth"
BTN_MENU      = "🏠 Menu"
