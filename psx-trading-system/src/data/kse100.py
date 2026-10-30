"""KSE-100 Index constituents — official PSX recomposition, effective 01-Apr-2026
(source: PSX notice "RE-COMPOSITION OF KSE100 & KSE100PR INDEX", Annexure A).

Each entry: (symbol, sector). A few micro-cap constituents (HBL Growth Fund,
DH Partners, Dolmen/TPL REITs, Pak-Gulf Leasing, Citi Pharma, Haleon, Lucky
Core, S.S. Oil, Ghandhara Automobiles) are not carried by the public
TradingView tape used for live prices, so they are omitted from the wheel —
they are tiny index weights and do not move the picture. Edit freely.
"""

KSE100 = [
    # ── Commercial banks ──
    ("UBL", "Commercial Banks"), ("BAHL", "Commercial Banks"), ("BAFL", "Commercial Banks"),
    ("BOP", "Commercial Banks"), ("FABL", "Commercial Banks"), ("MEBL", "Commercial Banks"),
    ("HBL", "Commercial Banks"), ("HMB", "Commercial Banks"), ("MCB", "Commercial Banks"),
    ("NBP", "Commercial Banks"), ("SCBPL", "Commercial Banks"), ("AKBL", "Commercial Banks"),
    ("ABL", "Commercial Banks"),
    # ── Oil & gas exploration ──
    ("OGDC", "Oil & Gas Exploration"), ("MARI", "Oil & Gas Exploration"),
    ("POL", "Oil & Gas Exploration"), ("PPL", "Oil & Gas Exploration"),
    # ── Oil & gas marketing ──
    ("PSO", "Oil & Gas Marketing"), ("APL", "Oil & Gas Marketing"),
    ("SNGP", "Oil & Gas Marketing"), ("SSGC", "Oil & Gas Marketing"),
    # ── Refinery ──
    ("ATRL", "Refinery"), ("CNERGY", "Refinery"),
    # ── Power generation & distribution ──
    ("HUBC", "Power"), ("KAPCO", "Power"), ("KEL", "Power"),
    # ── Fertilizer ──
    ("FFC", "Fertilizer"), ("EFERT", "Fertilizer"), ("AHCL", "Fertilizer"),
    ("FATIMA", "Fertilizer"),
    # ── Cement ──
    ("LUCK", "Cement"), ("DGKC", "Cement"), ("BWCL", "Cement"), ("FCCL", "Cement"),
    ("KOHC", "Cement"), ("CHCC", "Cement"), ("POWER", "Cement"), ("MLCF", "Cement"),
    ("PIOC", "Cement"),
    # ── Technology & communication ──
    ("SYS", "Technology & Comm."), ("AIRLINK", "Technology & Comm."),
    ("PTC", "Technology & Comm."), ("TRG", "Technology & Comm."),
    ("HUMNL", "Technology & Comm."),
    # ── Engineering ──
    ("ISL", "Engineering"), ("INIL", "Engineering"),
    # ── Automobile assembler ──
    ("MTL", "Automobiles"), ("INDU", "Automobiles"), ("SAZEW", "Automobiles"),
    ("ATLH", "Automobiles"), ("HCAR", "Automobiles"), ("GHNI", "Automobiles"),
    # ── Automobile parts ──
    ("THALL", "Auto Parts"), ("AGIL", "Auto Parts"),
    # ── Cables & electrical ──
    ("PAEL", "Cables & Electrical"),
    # ── Transport ─
    ("PIBTL", "Transport"),
    # ── Chemical ─
    ("LOTCHEM", "Chemical"), ("COLG", "Chemical"),
    # ── Pharmaceutical ──
    ("SEARL", "Pharmaceutical"), ("AGP", "Pharmaceutical"), ("GLAXO", "Pharmaceutical"),
    ("ABOT", "Pharmaceutical"), ("HINOON", "Pharmaceutical"),
    # ── Food & personal care ──
    ("NESTLE", "Food & Personal Care"), ("FFL", "Food & Personal Care"),
    ("MUREB", "Food & Personal Care"), ("NATF", "Food & Personal Care"),
    ("RMPL", "Food & Personal Care"), ("UPFL", "Food & Personal Care"),
    # ── Textile ──
    ("ILP", "Textile"), ("NML", "Textile"), ("KTML", "Textile"), ("YOUW", "Textile"),
    ("GADT", "Textile"), ("MEHT", "Textile"), ("BNWM", "Textile"), ("IBFL", "Textile"),
    # ── Other sectors ──
    ("PAKT", "Tobacco"), ("AICL", "Insurance"), ("FHAM", "Modaraba"),
    ("LPGL", "Leasing"), ("ENGROH", "Investment Cos."), ("PSX", "Investment Cos."),
    ("JDWS", "Sugar & Allied"), ("PKGS", "Paper & Board"), ("SRVI", "Leather"),
    ("TGL", "Glass & Ceramics"), ("GHGL", "Glass & Ceramics"),
    ("PSEL", "Miscellaneous"), ("PABC", "Miscellaneous"), ("SHFA", "Miscellaneous"),
    ("JVDC", "Property"),
]

SYMBOLS = [s for s, _ in KSE100]
SECTOR_OF = dict(KSE100)
