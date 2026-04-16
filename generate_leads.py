"""
generate_leads.py — runs inside GitHub Actions
Environment vars: APOLLO_API_KEY, RESEND_EXTERNAL_API_KEY,
                  AGENCY_EMAIL, AGENCY_NAME, SPECIALTY, CITY
"""
import os, sys, json, requests
from datetime import date

APOLLO_KEY = os.environ['APOLLO_API_KEY']
RESEND_KEY = os.environ['RESEND_EXTERNAL_API_KEY']
AGENCY_EMAIL = os.environ.get('AGENCY_EMAIL', '')
AGENCY_NAME  = os.environ.get('AGENCY_NAME', 'der')
SPECIALTY    = os.environ.get('SPECIALTY', 'seo')
CITY         = os.environ.get('CITY', 'Denmark')

APOLLO_HEADERS = {
    'X-Api-Key': APOLLO_KEY,
    'Cache-Control': 'no-cache',
    'Content-Type': 'application/json',
}

KEYWORD_MAP = {
    'google-ads':      ['e-commerce', 'retail', 'webshop', 'automotive', 'food & beverages'],
    'seo':             ['retail', 'hospitality', 'real estate', 'construction', 'food & beverages'],
    'webdesign':       ['retail', 'restaurant', 'professional services', 'construction', 'health'],
    'social-media':    ['fashion', 'restaurant', 'fitness', 'retail', 'beauty'],
    'email-marketing': ['retail', 'e-commerce', 'consumer goods', 'fashion'],
    'branding':        ['consumer goods', 'fashion', 'food & beverages', 'professional services'],
    'performance':     ['retail', 'e-commerce', 'consumer goods', 'travel'],
}

NEED_MAP = {
    'google-ads':      'Google Ads og betalt annoncering',
    'seo':             'Søgemaskineoptimering (SEO)',
    'webdesign':       'Nyt website eller webshop',
    'social-media':    'Social media management',
    'email-marketing': 'Email marketing og automation',
    'branding':        'Branding og visuel identitet',
    'performance':     'Performance marketing og tracking',
}


def search_candidates(specialty, city, n=15):
    keywords = KEYWORD_MAP.get(specialty, ['retail', 'construction'])
    location = f"{city}, Denmark" if city.lower() not in ('denmark', '') else 'Denmark'
    r = requests.post(
        'https://api.apollo.io/api/v1/mixed_people/api_search',
        headers=APOLLO_HEADERS,
        json={
            'organization_locations': [location],
            'person_seniorities': ['owner', 'founder', 'c_suite'],
            'person_titles': ['owner', 'founder', 'CEO', 'ejer', 'direktør'],
            'organization_num_employees_ranges': ['1,30'],
            'q_organization_keyword_tags': keywords,
            'per_page': n,
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get('people', [])


def enrich(apollo_id):
    r = requests.post(
        'https://api.apollo.io/api/v1/people/match',
        headers=APOLLO_HEADERS,
        json={'id': apollo_id},
        timeout=20,
    )
    r.raise_for_status()
    return r.json().get('person')


def infer_need(specialty, org):
    kw  = ' '.join(org.get('keywords', [])).lower()
    ind = (org.get('industry') or '').lower()
    base = NEED_MAP.get(specialty, 'Digital markedsføring')
    if 'shopify' in kw or 'woocommerce' in kw or 'webshop' in kw:
        return f'E-commerce optimering + {base}'
    if 'restaurant' in ind or 'food' in ind:
        return f'Lokal synlighed + {base}'
    if 'construction' in ind or 'real estate' in ind:
        return f'Lead gen + {base}'
    return base


def generate(specialty, city, count=5):
    candidates = search_candidates(specialty, city, count * 3)
    leads = []
    for p in candidates:
        if len(leads) >= count: break
        if not p.get('has_email'): continue
        try:
            enriched = enrich(p['id'])
            if not enriched or not enriched.get('email'): continue
            org = enriched.get('organization') or {}
            leads.append({
                'company':      org.get('name', '—'),
                'industry':     org.get('industry', '—'),
                'employees':    org.get('estimated_num_employees', '—'),
                'city':         enriched.get('city') or org.get('city', '—'),
                'website':      org.get('website_url', ''),
                'contact_name': f"{enriched['first_name']} {enriched['last_name']}",
                'title':        enriched.get('title', '—'),
                'email':        enriched['email'],
                'phone':        org.get('phone', ''),
                'linkedin':     enriched.get('linkedin_url', ''),
                'need':         infer_need(specialty, org),
            })
        except Exception as e:
            print(f'  skip: {e}')
    return leads


def send_email(to, name, specialty, leads):
    def row(l, i):
        bg = '#f9fafb' if i % 2 == 0 else '#fff'
        ph = f'<br><small style="color:#6B7280">{l["phone"]}</small>' if l.get('phone') else ''
        li = f'<br><a href="{l["linkedin"]}" style="color:#6B7280;font-size:12px">LinkedIn</a>' if l.get('linkedin') else ''
        ws = f'<a href="{l["website"]}" style="font-size:12px;color:#2563EB">{l["website"][:40]}</a><br>' if l.get('website') else ''
        return f'''<tr style="background:{bg}">
<td style="padding:14px 16px;border-bottom:1px solid #f3f4f6">
  <strong>{l["company"]}</strong><br>
  <small style="color:#6B7280">{l["industry"]} · {l["city"]} · {l["employees"]} ansatte</small><br>
  {ws}
</td>
<td style="padding:14px 16px;border-bottom:1px solid #f3f4f6">
  {l["contact_name"]}<br><small style="color:#6B7280">{l["title"]}</small>
</td>
<td style="padding:14px 16px;border-bottom:1px solid #f3f4f6">
  <a href="mailto:{l["email"]}" style="color:#2563EB">{l["email"]}</a>{ph}{li}
</td>
<td style="padding:14px 16px;border-bottom:1px solid #f3f4f6;font-size:13px;color:#374151">{l["need"]}</td>
</tr>'''

    rows = ''.join(row(l, i) for i, l in enumerate(leads))
    today = date.today().strftime('%d/%m/%Y')
    n = len(leads)

    html = f"""<!DOCTYPE html><html lang="da"><head><meta charset="UTF-8">
<style>
body{{font-family:system-ui,sans-serif;background:#f3f4f6;margin:0;padding:32px 16px}}
.card{{max-width:900px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,.07)}}
.hd{{background:#2563EB;color:#fff;padding:32px 40px}}
.hd h1{{margin:0;font-size:22px;font-weight:800}}.hd p{{margin:6px 0 0;opacity:.85}}
.bd{{padding:32px 40px}}
table{{width:100%;border-collapse:collapse;font-size:14px}}
th{{background:#f3f4f6;padding:10px 16px;text-align:left;font-size:11px;text-transform:uppercase;color:#6B7280}}
.cta{{display:inline-block;margin-top:24px;background:#2563EB;color:#fff;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:700}}
.ft{{padding:20px 40px;border-top:1px solid #f3f4f6;font-size:12px;color:#9CA3AF;text-align:center}}
</style></head><body>
<div class="card">
  <div class="hd">
    <h1>⚡ Dine {n} leads fra BUKA</h1>
    <p>Specialitet: <strong>{specialty}</strong> · {today}</p>
  </div>
  <div class="bd">
    <p style="color:#374151;margin:0 0 20px">Hej {name},<br><br>
    Her er dine leads — danske SMV'er der matcher din specialitet. Alle emails er verificerede. Kontakt dem direkte.</p>
    <table>
      <thead><tr>
        <th>Virksomhed</th><th>Kontaktperson</th><th>Email / Tlf</th><th>Sandsynligt behov</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>
    <p style="margin-top:24px;color:#374151;font-size:14px">Eksklusivt til dig i <strong>30 dage</strong>.</p>
    <a href="mailto:esben@buka.dk?subject=Bestil+flere+leads" class="cta">Bestil flere leads →</a>
  </div>
  <div class="ft">BUKA · esben@buka.dk</div>
</div></body></html>"""

    r = requests.post(
        'https://api.resend.com/emails',
        headers={'Authorization': f'Bearer {RESEND_KEY}', 'Content-Type': 'application/json'},
        json={
            'from': 'BUKA <esben@buka.dk>',
            'to': [to],
            'subject': f'Dine {n} leads fra BUKA',
            'html': html,
        },
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


if __name__ == '__main__':
    if not AGENCY_EMAIL:
        print('ERROR: AGENCY_EMAIL not set')
        sys.exit(1)

    print(f'Generating leads: specialty={SPECIALTY} city={CITY} for {AGENCY_EMAIL}')
    leads = generate(SPECIALTY, CITY, 5)

    if not leads:
        print('ERROR: No leads generated')
        sys.exit(1)

    print(f'Generated {len(leads)} leads:')
    for l in leads:
        print(f'  - {l["company"]} | {l["contact_name"]} | {l["email"]}')

    result = send_email(AGENCY_EMAIL, AGENCY_NAME, SPECIALTY, leads)
    print(f'Email sent: {result}')
