/**
 * Country reference data (French names + international dial codes), used by
 * the public registration form for the nationality autocomplete and the
 * mandatory phone country-code selector.
 */
export interface Country {
  name: string
  iso2: string
  dialCode: string
}

export const COUNTRIES: Country[] = [
  { name: 'Afghanistan', iso2: 'AF', dialCode: '+93' },
  { name: 'Afrique du Sud', iso2: 'ZA', dialCode: '+27' },
  { name: 'Albanie', iso2: 'AL', dialCode: '+355' },
  { name: 'Algérie', iso2: 'DZ', dialCode: '+213' },
  { name: 'Allemagne', iso2: 'DE', dialCode: '+49' },
  { name: 'Andorre', iso2: 'AD', dialCode: '+376' },
  { name: 'Angola', iso2: 'AO', dialCode: '+244' },
  { name: 'Arabie Saoudite', iso2: 'SA', dialCode: '+966' },
  { name: 'Argentine', iso2: 'AR', dialCode: '+54' },
  { name: 'Arménie', iso2: 'AM', dialCode: '+374' },
  { name: 'Australie', iso2: 'AU', dialCode: '+61' },
  { name: 'Autriche', iso2: 'AT', dialCode: '+43' },
  { name: 'Azerbaïdjan', iso2: 'AZ', dialCode: '+994' },
  { name: 'Bahreïn', iso2: 'BH', dialCode: '+973' },
  { name: 'Bangladesh', iso2: 'BD', dialCode: '+880' },
  { name: 'Belgique', iso2: 'BE', dialCode: '+32' },
  { name: 'Bénin', iso2: 'BJ', dialCode: '+229' },
  { name: 'Biélorussie', iso2: 'BY', dialCode: '+375' },
  { name: 'Birmanie (Myanmar)', iso2: 'MM', dialCode: '+95' },
  { name: 'Bolivie', iso2: 'BO', dialCode: '+591' },
  { name: 'Bosnie-Herzégovine', iso2: 'BA', dialCode: '+387' },
  { name: 'Botswana', iso2: 'BW', dialCode: '+267' },
  { name: 'Brésil', iso2: 'BR', dialCode: '+55' },
  { name: 'Brunei', iso2: 'BN', dialCode: '+673' },
  { name: 'Bulgarie', iso2: 'BG', dialCode: '+359' },
  { name: 'Burkina Faso', iso2: 'BF', dialCode: '+226' },
  { name: 'Burundi', iso2: 'BI', dialCode: '+257' },
  { name: 'Cambodge', iso2: 'KH', dialCode: '+855' },
  { name: 'Cameroun', iso2: 'CM', dialCode: '+237' },
  { name: 'Canada', iso2: 'CA', dialCode: '+1' },
  { name: 'Cap-Vert', iso2: 'CV', dialCode: '+238' },
  { name: 'Chili', iso2: 'CL', dialCode: '+56' },
  { name: 'Chine', iso2: 'CN', dialCode: '+86' },
  { name: 'Chypre', iso2: 'CY', dialCode: '+357' },
  { name: 'Colombie', iso2: 'CO', dialCode: '+57' },
  { name: 'Comores', iso2: 'KM', dialCode: '+269' },
  { name: 'Congo (Brazzaville)', iso2: 'CG', dialCode: '+242' },
  { name: 'Congo (RDC)', iso2: 'CD', dialCode: '+243' },
  { name: 'Corée du Nord', iso2: 'KP', dialCode: '+850' },
  { name: 'Corée du Sud', iso2: 'KR', dialCode: '+82' },
  { name: 'Costa Rica', iso2: 'CR', dialCode: '+506' },
  { name: 'Côte d\'Ivoire', iso2: 'CI', dialCode: '+225' },
  { name: 'Croatie', iso2: 'HR', dialCode: '+385' },
  { name: 'Cuba', iso2: 'CU', dialCode: '+53' },
  { name: 'Danemark', iso2: 'DK', dialCode: '+45' },
  { name: 'Djibouti', iso2: 'DJ', dialCode: '+253' },
  { name: 'Égypte', iso2: 'EG', dialCode: '+20' },
  { name: 'Émirats Arabes Unis', iso2: 'AE', dialCode: '+971' },
  { name: 'Équateur', iso2: 'EC', dialCode: '+593' },
  { name: 'Érythrée', iso2: 'ER', dialCode: '+291' },
  { name: 'Espagne', iso2: 'ES', dialCode: '+34' },
  { name: 'Estonie', iso2: 'EE', dialCode: '+372' },
  { name: 'Eswatini', iso2: 'SZ', dialCode: '+268' },
  { name: 'États-Unis', iso2: 'US', dialCode: '+1' },
  { name: 'Éthiopie', iso2: 'ET', dialCode: '+251' },
  { name: 'Fidji', iso2: 'FJ', dialCode: '+679' },
  { name: 'Finlande', iso2: 'FI', dialCode: '+358' },
  { name: 'France', iso2: 'FR', dialCode: '+33' },
  { name: 'Gabon', iso2: 'GA', dialCode: '+241' },
  { name: 'Gambie', iso2: 'GM', dialCode: '+220' },
  { name: 'Géorgie', iso2: 'GE', dialCode: '+995' },
  { name: 'Ghana', iso2: 'GH', dialCode: '+233' },
  { name: 'Grèce', iso2: 'GR', dialCode: '+30' },
  { name: 'Guatemala', iso2: 'GT', dialCode: '+502' },
  { name: 'Guinée', iso2: 'GN', dialCode: '+224' },
  { name: 'Guinée équatoriale', iso2: 'GQ', dialCode: '+240' },
  { name: 'Guinée-Bissau', iso2: 'GW', dialCode: '+245' },
  { name: 'Haïti', iso2: 'HT', dialCode: '+509' },
  { name: 'Honduras', iso2: 'HN', dialCode: '+504' },
  { name: 'Hongrie', iso2: 'HU', dialCode: '+36' },
  { name: 'Inde', iso2: 'IN', dialCode: '+91' },
  { name: 'Indonésie', iso2: 'ID', dialCode: '+62' },
  { name: 'Irak', iso2: 'IQ', dialCode: '+964' },
  { name: 'Iran', iso2: 'IR', dialCode: '+98' },
  { name: 'Irlande', iso2: 'IE', dialCode: '+353' },
  { name: 'Islande', iso2: 'IS', dialCode: '+354' },
  { name: 'Israël', iso2: 'IL', dialCode: '+972' },
  { name: 'Italie', iso2: 'IT', dialCode: '+39' },
  { name: 'Jamaïque', iso2: 'JM', dialCode: '+1876' },
  { name: 'Japon', iso2: 'JP', dialCode: '+81' },
  { name: 'Jordanie', iso2: 'JO', dialCode: '+962' },
  { name: 'Kazakhstan', iso2: 'KZ', dialCode: '+7' },
  { name: 'Kenya', iso2: 'KE', dialCode: '+254' },
  { name: 'Kirghizistan', iso2: 'KG', dialCode: '+996' },
  { name: 'Kosovo', iso2: 'XK', dialCode: '+383' },
  { name: 'Koweït', iso2: 'KW', dialCode: '+965' },
  { name: 'Laos', iso2: 'LA', dialCode: '+856' },
  { name: 'Lesotho', iso2: 'LS', dialCode: '+266' },
  { name: 'Lettonie', iso2: 'LV', dialCode: '+371' },
  { name: 'Liban', iso2: 'LB', dialCode: '+961' },
  { name: 'Liberia', iso2: 'LR', dialCode: '+231' },
  { name: 'Libye', iso2: 'LY', dialCode: '+218' },
  { name: 'Liechtenstein', iso2: 'LI', dialCode: '+423' },
  { name: 'Lituanie', iso2: 'LT', dialCode: '+370' },
  { name: 'Luxembourg', iso2: 'LU', dialCode: '+352' },
  { name: 'Macédoine du Nord', iso2: 'MK', dialCode: '+389' },
  { name: 'Madagascar', iso2: 'MG', dialCode: '+261' },
  { name: 'Malaisie', iso2: 'MY', dialCode: '+60' },
  { name: 'Malawi', iso2: 'MW', dialCode: '+265' },
  { name: 'Maldives', iso2: 'MV', dialCode: '+960' },
  { name: 'Mali', iso2: 'ML', dialCode: '+223' },
  { name: 'Malte', iso2: 'MT', dialCode: '+356' },
  { name: 'Maroc', iso2: 'MA', dialCode: '+212' },
  { name: 'Maurice', iso2: 'MU', dialCode: '+230' },
  { name: 'Mauritanie', iso2: 'MR', dialCode: '+222' },
  { name: 'Mexique', iso2: 'MX', dialCode: '+52' },
  { name: 'Moldavie', iso2: 'MD', dialCode: '+373' },
  { name: 'Monaco', iso2: 'MC', dialCode: '+377' },
  { name: 'Mongolie', iso2: 'MN', dialCode: '+976' },
  { name: 'Monténégro', iso2: 'ME', dialCode: '+382' },
  { name: 'Mozambique', iso2: 'MZ', dialCode: '+258' },
  { name: 'Namibie', iso2: 'NA', dialCode: '+264' },
  { name: 'Népal', iso2: 'NP', dialCode: '+977' },
  { name: 'Nicaragua', iso2: 'NI', dialCode: '+505' },
  { name: 'Niger', iso2: 'NE', dialCode: '+227' },
  { name: 'Nigeria', iso2: 'NG', dialCode: '+234' },
  { name: 'Norvège', iso2: 'NO', dialCode: '+47' },
  { name: 'Nouvelle-Zélande', iso2: 'NZ', dialCode: '+64' },
  { name: 'Oman', iso2: 'OM', dialCode: '+968' },
  { name: 'Ouganda', iso2: 'UG', dialCode: '+256' },
  { name: 'Ouzbékistan', iso2: 'UZ', dialCode: '+998' },
  { name: 'Pakistan', iso2: 'PK', dialCode: '+92' },
  { name: 'Panama', iso2: 'PA', dialCode: '+507' },
  { name: 'Papouasie-Nouvelle-Guinée', iso2: 'PG', dialCode: '+675' },
  { name: 'Paraguay', iso2: 'PY', dialCode: '+595' },
  { name: 'Pays-Bas', iso2: 'NL', dialCode: '+31' },
  { name: 'Pérou', iso2: 'PE', dialCode: '+51' },
  { name: 'Philippines', iso2: 'PH', dialCode: '+63' },
  { name: 'Pologne', iso2: 'PL', dialCode: '+48' },
  { name: 'Portugal', iso2: 'PT', dialCode: '+351' },
  { name: 'Qatar', iso2: 'QA', dialCode: '+974' },
  { name: 'République Centrafricaine', iso2: 'CF', dialCode: '+236' },
  { name: 'République Dominicaine', iso2: 'DO', dialCode: '+1809' },
  { name: 'République Tchèque', iso2: 'CZ', dialCode: '+420' },
  { name: 'Roumanie', iso2: 'RO', dialCode: '+40' },
  { name: 'Royaume-Uni', iso2: 'GB', dialCode: '+44' },
  { name: 'Russie', iso2: 'RU', dialCode: '+7' },
  { name: 'Rwanda', iso2: 'RW', dialCode: '+250' },
  { name: 'Salvador', iso2: 'SV', dialCode: '+503' },
  { name: 'Samoa', iso2: 'WS', dialCode: '+685' },
  { name: 'Sénégal', iso2: 'SN', dialCode: '+221' },
  { name: 'Serbie', iso2: 'RS', dialCode: '+381' },
  { name: 'Seychelles', iso2: 'SC', dialCode: '+248' },
  { name: 'Sierra Leone', iso2: 'SL', dialCode: '+232' },
  { name: 'Singapour', iso2: 'SG', dialCode: '+65' },
  { name: 'Slovaquie', iso2: 'SK', dialCode: '+421' },
  { name: 'Slovénie', iso2: 'SI', dialCode: '+386' },
  { name: 'Somalie', iso2: 'SO', dialCode: '+252' },
  { name: 'Soudan', iso2: 'SD', dialCode: '+249' },
  { name: 'Soudan du Sud', iso2: 'SS', dialCode: '+211' },
  { name: 'Sri Lanka', iso2: 'LK', dialCode: '+94' },
  { name: 'Suède', iso2: 'SE', dialCode: '+46' },
  { name: 'Suisse', iso2: 'CH', dialCode: '+41' },
  { name: 'Suriname', iso2: 'SR', dialCode: '+597' },
  { name: 'Syrie', iso2: 'SY', dialCode: '+963' },
  { name: 'Tadjikistan', iso2: 'TJ', dialCode: '+992' },
  { name: 'Tanzanie', iso2: 'TZ', dialCode: '+255' },
  { name: 'Tchad', iso2: 'TD', dialCode: '+235' },
  { name: 'Thaïlande', iso2: 'TH', dialCode: '+66' },
  { name: 'Timor Oriental', iso2: 'TL', dialCode: '+670' },
  { name: 'Togo', iso2: 'TG', dialCode: '+228' },
  { name: 'Tonga', iso2: 'TO', dialCode: '+676' },
  { name: 'Trinité-et-Tobago', iso2: 'TT', dialCode: '+1868' },
  { name: 'Tunisie', iso2: 'TN', dialCode: '+216' },
  { name: 'Turkménistan', iso2: 'TM', dialCode: '+993' },
  { name: 'Turquie', iso2: 'TR', dialCode: '+90' },
  { name: 'Ukraine', iso2: 'UA', dialCode: '+380' },
  { name: 'Uruguay', iso2: 'UY', dialCode: '+598' },
  { name: 'Vanuatu', iso2: 'VU', dialCode: '+678' },
  { name: 'Vatican', iso2: 'VA', dialCode: '+379' },
  { name: 'Venezuela', iso2: 'VE', dialCode: '+58' },
  { name: 'Vietnam', iso2: 'VN', dialCode: '+84' },
  { name: 'Yémen', iso2: 'YE', dialCode: '+967' },
  { name: 'Zambie', iso2: 'ZM', dialCode: '+260' },
  { name: 'Zimbabwe', iso2: 'ZW', dialCode: '+263' },
]

function normalize(s: string): string {
  return s
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .trim()
}

/** Cheap Levenshtein distance — good enough for short country names, no dependency needed. */
function levenshtein(a: string, b: string): number {
  const m = a.length, n = b.length
  if (m === 0) return n
  if (n === 0) return m
  const dp: number[] = Array.from({ length: n + 1 }, (_, j) => j)
  for (let i = 1; i <= m; i++) {
    let prev = dp[0]
    dp[0] = i
    for (let j = 1; j <= n; j++) {
      const tmp = dp[j]
      dp[j] = a[i - 1] === b[j - 1] ? prev : 1 + Math.min(prev, dp[j], dp[j - 1])
      prev = tmp
    }
  }
  return dp[n]
}

/**
 * Country name suggestions "closest to" the query: exact/prefix/substring
 * matches first (handles normal typing), falling back to edit-distance when
 * nothing contains the query at all (handles typos like "Belgik").
 */
export function suggestCountries(query: string, limit = 8): Country[] {
  const q = normalize(query)
  if (!q) return COUNTRIES.slice(0, limit)

  const scored = COUNTRIES.map((c) => {
    const n = normalize(c.name)
    let score = 0
    if (n === q) score = 100
    else if (n.startsWith(q)) score = 90
    else if (n.includes(q)) score = 70
    else if (n.split(/[\s'-]+/).some((w) => w.startsWith(q))) score = 60
    return { c, score }
  })

  const direct = scored.filter((s) => s.score > 0).sort((a, b) => b.score - a.score)
  if (direct.length > 0) return direct.slice(0, limit).map((s) => s.c)

  // Nothing matched directly (likely a typo) — rank by edit distance instead.
  return COUNTRIES
    .map((c) => ({ c, dist: levenshtein(q, normalize(c.name).slice(0, q.length + 3)) }))
    .sort((a, b) => a.dist - b.dist)
    .slice(0, limit)
    .map((s) => s.c)
}
