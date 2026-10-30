"""Curated qualitative intelligence for major PSX companies + sector templates.

Entries are analyst-style one-liners (business model, moat, customers, pros,
cons). Anything not curated falls back to its sector template, and the agents
layer data-driven signals (ROE, leverage, growth, dividends) on top so every
listed company still gets a complete, honest write-up.
"""

SECTOR_TEMPLATE = {
    "COMMERCIAL BANKS": dict(
        business="Earns from the spread between interest on loans/ investments and cost of deposits, plus fee income.",
        customers="Retail, corporate and SME borrowers; depositors; payment users.",
        moat="Licence + scale + deposit franchise; switching costs for borrowers.",
        pros=["Regulated, systemically important industry", "Net-interest income rises in high-rate environments", "Deep deposit bases are sticky"],
        cons=["Credit-risk cycles and NPLs", "Heavy taxation on financial income", "Rate-cut cycles squeeze spreads"]),
    "OIL & GAS EXPLORATION COMPANIES": dict(
        business="Explores and produces crude oil and gas; revenue tracks dollar-linked wellhead prices.",
        customers="Refineries (crude) and gas utilities / power sector (gas).",
        moat="Reserves + concession acreage; very high replacement cost for rivals.",
        pros=["Dollar-pegged revenue hedge", "High margins and cash flow", "Attractive dividend yields"],
        cons=["Circular debt & delayed GOF payments", "Depleting reserves without exploration", "Political pricing risk on gas"]),
    "FERTILIZER": dict(
        business="Makes urea/DAP fertilisers; earns on the gas-to-fertiliser price spread.",
        customers="Farmers via dealers/distributors nationwide.",
        moat="Scarce gas allocations + oligopoly capacity + distribution reach.",
        pros=["Oligopolistic market with pricing power", "Food-security demand is structural", "Consistent high payouts"],
        cons=["Gas curtailment/price shocks", "Government intervention on urea price", "Agriculture seasonality"]),
    "CEMENT": dict(
        business="Manufactures and sells cement; volume driven by construction activity.",
        customers="Dealers, contractors, developers, public-sector projects.",
        moat="Capacity scale + captive power cost advantage + brand in retail.",
        pros=["Beneficiary of infra/housing cycles", "Low debt after deleveraging leaders", "Export optionality"],
        cons=["Highly cyclical, rate-sensitive demand", "Coal price and PKR volatility hit margins", "Industry overcapacity in downturns"]),
    "OIL & GAS MARKETING COMPANIES": dict(
        business="Imports/refines-adjacent marketing of petroleum products; earns regulated + par-into-port margins.",
        customers="Retail fuel stations, industrial & aviation clients.",
        moat="Nationwide depot/network footprint and brand trust.",
        pros=["Volume grows with economy", "Working-capital disciplined majors", "Dividend consistency"],
        cons=["Margin set by regulator", "PKR depreciation raises import bills", "Long-term energy-transition risk"]),
    "POWER GENERATION & DISTRIBUTION": dict(
        business="Generates or distributes electricity under government-backed agreements.",
        customers="Grid / K-Electric consumers; CPPA-G for IPPs.",
        moat="Contracted capacity payments (IPP) or urban franchise (KEL).",
        pros=["Contracted cash flows for IPPs", "Indexation protections in many contracts", "High yields"],
        cons=["Receivables circular debt", "Regulatory and tariff politics", "Thermal fuel risk"]),
    "TECHNOLOGY & COMMUNICATION": dict(
        business="Digital services — telecom, software exports, platforms, device retail.",
        customers="Consumers, enterprises, overseas clients.",
        moat="Network effects / brand / data, varying by name.",
        pros=["Structural growth sector", "Some exporters earn in USD", "Young-market penetration"],
        cons=["Many unprofitable names", "Funding-rate sensitivity", "Execution risk"]),
    "PHARMACEUTICALS": dict(
        business="Formulates and sells medicines through hospitals and retail pharmacy.",
        customers="Patients via doctors, pharmacies, hospitals; some exports.",
        moat="Brand loyalty among prescribers + distribution + registrations.",
        pros=["Defensive healthcare demand", "Export upside for a few", "Decades-old trusted brands"],
        cons=["DRAP price caps on many SKUs", "Imported API cost vs PKR", "Working-capital intensity"]),
    "FOOD & PERSONAL CARE PRODUCTS": dict(
        business="Branded consumer foods/hygiene products with national distribution.",
        customers="Households via general trade + modern trade.",
        moat="Household brands + distribution muscle + multinationals' QA.",
        pros=["Pricing power of leading brands", "Defensive consumption", "Strong ROE names"],
        cons=["Input inflation squeezes margins", "Volume shocks on price hikes", "FX on imported inputs"]),
    "AUTOMOBILE ASSEMBLER": dict(
        business="Assembles vehicles from imported/ local parts; earns on localization spread.",
        customers="Retail buyers, fleets, dealers.",
        moat="Dealer network + assembly licences + brand resale value.",
        pros=["Huge under-ownership market long term", "New entrants bring competition & capex", "Cyclical upswings are violent"],
        cons=["Demand collapses with rates/PKR", "Policy whipsaw on imports", "Competition from new Chinese assemblers"]),
    "TEXTILE WEAVING": dict(
        business="Spins yarn / makes fabric for export and domestic mills.",
        customers="Export fabric/garment chain.",
        moat="Limited — cost and energy efficiency decide.",
        pros=["Export earnings in USD", "Energy-cost arbitrage winners", "Govt export incentives"],
        cons=["Global demand cycles", "Energy price spikes", "Thin, commoditised margins"]),
}

COMPANY_INTEL = {
    "ENGRO": dict(
        business="Conglomerate holding: fertiliser (Engro Fertilizers), foods (FrieslandCampina), energy, polymers, connectivity.",
        customers="Farmers, consumers, power sector, industrial buyers.",
        moat="Management factory + diversified cash engines + brand portfolio.",
        pros=["Best-in-class governance reputation", "Multiple growth engines", "Strong subsidiary dividends"],
        cons=["Holding-company discount", "Energy subsidiary cyclicality", "Capital calls into new ventures"]),
    "FFC": dict(
        business="Pakistan's largest urea maker; sells through a nationwide dealer network.",
        customers="Farmers/dealers; some export tenders.",
        moat="Low-cost gas contract + scale + brand 'Sona' urea.",
        pros=["Industry-leading margins and ROE", "Long history of uninterrupted payouts", "Net-cash balance sheet"],
        cons=["Gas allocation risk", "Urea price caps in election cycles", "Concentration in one product"]),
    "EFERT": dict(
        business="Urea + DAP producer (Kandhkot plant) with own gas arrangements.",
        customers="Farmers via distribution.",
        moat="Modern plant efficiency + gas supply agreements.",
        pros=["High payout yield", "Efficient new capacity", "Diversified product mix"],
        cons=["Gas curtailment seasons", "Policy pricing risk", "Leverage from past capex"]),
    "LUCK": dict(
        business="Lucky Cement — grey/white cement maker with power & mining diversification.",
        customers="Dealers, construction, exporters.",
        moat="Scale + captive power + export outlets (regional).",
        pros=["Top-2 capacity with cost leadership", "Diversified into power/chemicals", "Export hedge"],
        cons=["Cement cycle downswings", "Coal/FX cost swings", "Capex appetite dilutes yields"]),
    "DGKC": dict(
        business="DG Khan Cement — large northern + southern capacity, export-focused.",
        customers="Local dealers + export (Afghanistan/Africa/Middle East).",
        moat="Export logistics footprint + scale.",
        pros=["Export diversification", "Low-cost southern plant", "Cycle recovery leverage"],
        cons=["High leverage history", "Freight/coal cost exposure", "Cyclicality"]),
    "HBL": dict(
        business="Largest bank by assets: corporate, retail, Islamic and international banking.",
        customers="Government, corporates, retail, SME.",
        moat="Sovereign + corporate relationships + branch network + brand.",
        pros=["Systemic franchise, government business", "Strong deposit base", "Consistent dividend"],
        cons=["Government exposure concentration", "Taxation on banks", "Rate-cycle sensitivity"]),
    "UBL": dict(
        business="Retail-and-corporate bank with digital-first franchise.",
        customers="Retail, corporate, trade clients.",
        moat="Efficiency culture + technology + Best-in-class cost/income.",
        pros=["Top profitability metrics", "Disciplined capital allocation", "Digital lead"],
        cons=["Rate-cut margin pressure", "Competitive deposit market", "Regulatory caps"]),
    "MEBL": dict(
        business="Meezan — largest Islamic bank; fast-growing deposit and loan book.",
        customers="Retail & corporate seeking Shariah-compliant banking.",
        moat="First-mover Islamic brand + sticky deposit franchise.",
        pros=["Structural growth in Islamic banking share", "Premium growth with quality", "High ROE"],
        cons=["Valuation premium", "Islamic-window competition from big banks", "Rate cycle"],
        ),
    "BAFL": dict(business="Mid-tier bank focused on corporate/SME and trade finance.",
        customers="Corporates, SME, trade.", moat="Niche trade relationships.",
        pros=["High yield + growth", "Improved asset quality"], cons=["Smaller deposit base vs top-5", "Concentration risk"]),
    "OGDC": dict(
        business="State-owned largest E&P: crude + gas production across major fields.",
        customers="Refineries, gas utilities via government contracts.",
        moat="Largest reserve base + sovereign backing.",
        pros=["Deeply discounted vs reserves", "High dividend yield", "Dollar-linked revenues"],
        cons=["Circular debt receivables", "Depletion without big discoveries", "Government ownership overhang"]),
    "PPL": dict(
        business="Pakistan Petroleum — major gas & crude producer (Qadirpur, major stakes).",
        customers="Gas network, refineries.",
        moat="Long-life producing fields.",
        pros=["Low-cost gas production", "Strong yield", "Exploration optionality"],
        cons=["Receivables delays", "Wellhead price policy", "Depletion"]),
    "MARI": dict(
        business="Mari Energies — gas producer with growing E&P portfolio & power exposure.",
        customers="Gas grid; power sector.",
        moat="Low-decline fields + management execution.",
        pros=["Growth via new blocks", "Healthy dividend growth", "Efficient operator"],
        cons=["Gas pricing politics", "Receivables", "Exploration risk"]),
    "PSO": dict(
        business="Largest fuel marketer ~50% market share; imports & distributes POL.",
        customers="Retail stations, aviation, industry.",
        moat="Unmatched depot/retail network + state trust.",
        pros=["Market leader with scale moat", "Volumes recover with economy", "Yield + asset value"],
        cons=["Huge receivables from circular debt", "Thin regulated margins", "Import FX risk"]),
    "HUBC": dict(
        business="Largest private IPP: coal + thermal + renewables portfolio.",
        customers="CPPA-G (government) under capacity-payment contracts.",
        moat="Long-term contracted capacity payments.",
        pros=["Contracted dollar-indexed cash flows", "High yield", "Diversifying into renewables/mining"],
        cons=["Sovereign receivable risk", "Coal phase-down narrative", "Refinancing needs"]),
    "KEL": dict(
        business="K-Electric — vertically integrated utility serving Karachi.",
        customers="3M+ consumers in Karachi.",
        moat="Urban monopoly franchise.",
        pros=["Karachi demand growth", "Tariff mechanism exists", "Acquisition interest history"],
        cons=["Fuel mix cost", "Regulatory lag on tariffs", "Heavy capex needs"]),
    "NESTLE": dict(
        business="MNC consumer foods: dairy, culinary, beverages, water.",
        customers="Households nationwide.",
        moat="Iconic brands + distribution + QA systems.",
        pros=["Unrivaled brand equity", "Pricing power", "Defensive demand"],
        cons=["Margin pressure in inflation", "Imported input FX", "Growth saturation in categories"]),
    "SYS": dict(
        business="Systems Ltd — software services exporter (North America/UK clients).",
        customers="Global enterprises.",
        moat="Talent scale + client stickiness + delivery track record.",
        pros=["USD revenues, PKR costs = structural margin", "AI-era services demand", "Zero-debt growth"],
        cons=["Client concentration", "Wage inflation", "Rich valuation vs PSX peers"]),
    "TRG": dict(
        business="Technology holding: BPO (eClerx associate), digital platforms, investments.",
        customers="Global outsourcing clients; consumers.",
        moat="Stake in eClerx + cash war-chest.",
        pros=["Asset-backed valuation", "Digital optionality"], cons=["Governance perception discount", "Volatile earnings mix"]),
    "AIRLINK": dict(
        business="Handset assembler/distributor (Samsung, Apple, Xiaomi, Infinix).",
        customers="Retail chains, consumers.",
        moat="Brand partnerships + assembly licence.",
        pros=["Smartphone penetration growth", "Local assembly margins", "High revenue growth"],
        cons=["Thin distribution margins", "Import policy shocks", "Working-capital heavy"]),
    "MTL": dict(
        business="Millat Tractors — Massey-branded tractors, >50% market share.",
        customers="Farmers via dealers.",
        moat="Dominant brand + dealer + parts network.",
        pros=["Pricing power in rural economy", "High ROE and payouts", "Export attempts"],
        cons=["Tractor cycle tied to crops/credit", "Competition from Ghazi/Chinese", "Input steel prices"]),
    "ATLH": dict(
        business="Atlas Honda — leading motorcycle maker (Honda JV).",
        customers="Retail riders via dealers.",
        moat="Honda brand + resale value + dealer network.",
        pros=["Market leadership", "Strong cash generation", "High payout"],
        cons=["Bike demand hit by inflation", "Japanese partner conservatism", "Competition from Chinese EV bikes looming"]),
    "PAEL": dict(
        business="Pak Elektron — wires & cables + home appliances (life brand).",
        customers="Construction, utilities, retail.",
        moat="Utility vendor relationships + brand revival.",
        pros=["Housing & grid spending tailwind", "Appliance turnaround"], cons=["Copper price/FX", "Competition in appliances"]),
    "SEARL": dict(
        business="Searle — branded pharmaceuticals (cardio, antibiotics, derm).",
        customers="Hospitals, pharmacies.",
        moat="Prescriber trust in chronic-care brands.",
        pros=["Brand portfolio", "Export growth attempts"], cons=["Price caps", "FX on APIs"]),
    "AGP": dict(
        business="AGP — one of largest local pharma manufacturers by volume.",
        customers="Retail + hospital pharmacy.",
        moat="Scale + wide SKU portfolio.",
        pros=["Volume leader", "Gradual price corrections"], cons=["Margin regulation", "Input FX"]),
    "FATIMA": dict(
        business="Fatima Fertilizers — modern urea/NPK complex.",
        customers="Farmers.",
        moat="Newest efficient plant + gas contract.",
        pros=["Efficiency leader", "Growing payouts"], cons=["Gas risk", "Leverage history"]),
    "AKBL": dict(
        business="Allied Bank — corporate & agro-focused universal bank.",
        customers="Corporate, agro, retail.",
        moat="Agri belt relationships.",
        pros=["High dividend yield", "Clean balance sheet"], cons=["Slow growth vs peers", "Ownership overhang history"]),
    "POL": dict(
        business="Pakistan Oilfields — mid-size E&P with stable mature fields.",
        customers="Refineries/gas network.", moat="Long-life low-decline fields.",
        pros=["Very high yield", "Low capex needs"], cons=["Depletion", "Receivables"]),
    "APL": dict(
        business="Attock Petroleum — fuel marketing + lubricants.",
        customers="Retail stations.", moat="Attock group refining linkage.",
        pros=["Growth in network", "Group synergies"], cons=["Small scale vs PSO", "Margin regulation"]),
    "CNERGY": dict(
        business="Cnergyico — refinery (Byco legacy) + marketing; capacity expansion underway.",
        customers="Fuel wholesalers/retail.", moat="Deep-sea port refinery logistics.",
        pros=["IMF-complex upgrade optionality", "Volume growth"], cons=["Thin refining margins", "High leverage", "FX debt"]),
    "ATRL": dict(
        business="Attock Refinery — complex refinery earning on cracks spreads.",
        customers="OMCs.", moat="Complexity + location.",
        pros=["Margin recovery cycles", "Group strength"], cons=["Crude FX", "Import policy"]),
    "FCCL": dict(
        business="Fauji Cement — northern/southern capacity + power ventures.",
        customers="Dealers/export.", moat="Fauji brand + logistics.",
        pros=["Balanced domestic/export", "Low debt"], cons=["Cycle", "Coal costs"]),
    "KOHC": dict(
        business="Kohat Cement — northern player, strong local brand.",
        customers="NW dealers.", moat="Regional dominance.",
        pros=["Regional pricing strength", "Export to Afghanistan"], cons=["Single-region concentration", "Cycle"]),
    "NBP": dict(
        business="National Bank — government business + huge branch network.",
        customers="Government, public sector, retail.", moat="State payroll & treasury franchise.",
        pros=["Cheap deposits", "High yield"], cons=["Governance/political interference history", "Efficiency"]),
    "MCB": dict(
        business="MCB Bank — conservative, high-quality commercial bank.",
        customers="Retail/corporate.", moat="Culture of prudence + Nishat backing.",
        pros=["Best asset-quality history", "Strong payouts"], cons=["Slow loan growth conservatism", "Rate cycle"]),
    "BAHL": dict(
        business="Bank Alfalah — retail & Islamic banking growth (ABD group).",
        customers="Retail, SME.", moat="Group ecosystem + digital push.",
        pros=["Growth franchise", "Islamic banking scale"], cons=["Rate cycle", "Competition"]),
    "INDU": dict(
        business="Indus Motor — Toyota assembler (IMC).",
        customers="Retail car buyers.", moat="Toyota brand resale value.",
        pros=["Brand trust", "New model launches"], cons=["Auto cycle", "Import policy", "Competition"]),
    "HCAR": dict(
        business="Honda Atlas Cars — sedan assembler.",
        customers="Retail.", moat="Honda reliability brand.",
        pros=["High payouts in good years"], cons=["Model refresh lag", "Cyclicality"]),
    "JDWS": dict(
        business="JDW Sugar — sugar + power cogeneration (largest mill).",
        customers="Industrial/consumer sugar; grid power.", moat="Scale + captive bagasse power.",
        pros=["Sugar cycle upside", "Power side cash"], cons=["Export restrictions", "Cane price politics"]),
    "BNWM": dict(
        business="Bunny's / Banwa? — textile composite unit (spinning→fabric).",
        customers="Export garment chain.", moat="Integrated chain.",
        pros=["USD earnings", "Energy deals"], cons=["Global cycle", "Margins thin"]),
}

MANAGEMENT_NOTES = {
    "default": "Assessed quantitatively: capital-allocation record (ROE & reinvestment), payout discipline, leverage trend and insider alignment (free feeds rarely disclose PSX insider trades, so ownership data comes from Yahoo where published).",
}
