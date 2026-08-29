#!/usr/bin/env python3
import json
import shutil
import subprocess
from pathlib import Path

BASE = Path('/home/ubuntu/vendor-reputation-service')
BASE.mkdir(parents=True, exist_ok=True)
(BASE / 'app').mkdir(exist_ok=True)
(BASE / 'sql').mkdir(exist_ok=True)
(BASE / 'docs').mkdir(exist_ok=True)

(BASE / 'README.md').write_text(
    '# Vendor Reputation Service\n\n'
    'Canonical domain service for vendor identity, evidence, reviews, and derived reputation.\n\n'
    'Consumers such as studio-web must use the service API instead of owning vendor domain data.\n',
    encoding='utf-8',
)

(BASE / 'sql' / '001_initial.sql').write_text(r'''CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS vendors (
  id uuid PRIMARY KEY,
  canonical_name text NOT NULL,
  status text NOT NULL DEFAULT 'active',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS vendor_aliases (
  id bigserial PRIMARY KEY,
  vendor_id uuid NOT NULL REFERENCES vendors(id) ON DELETE CASCADE,
  alias text NOT NULL,
  UNIQUE(vendor_id, alias)
);
CREATE TABLE IF NOT EXISTS evidence (
  id uuid PRIMARY KEY,
  source_type text NOT NULL,
  source_url text NOT NULL,
  source_object_id text,
  observed_at timestamptz,
  original_text text,
  review_status text NOT NULL DEFAULT 'pending',
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(source_type, source_url)
);
CREATE TABLE IF NOT EXISTS vendor_mentions (
  id bigserial PRIMARY KEY,
  evidence_id uuid NOT NULL REFERENCES evidence(id) ON DELETE CASCADE,
  vendor_id uuid REFERENCES vendors(id) ON DELETE SET NULL,
  extracted_name text,
  service_category text,
  region text,
  signal text NOT NULL DEFAULT 'unclear',
  confidence numeric(4,3),
  review_status text NOT NULL DEFAULT 'pending'
);
CREATE TABLE IF NOT EXISTS reviews (
  id uuid PRIMARY KEY,
  vendor_id uuid NOT NULL REFERENCES vendors(id) ON DELETE CASCADE,
  evidence_id uuid REFERENCES evidence(id) ON DELETE SET NULL,
  rating numeric(2,1) CHECK (rating >= 1 AND rating <= 5),
  body text,
  occurred_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS reputation_policies (
  id text PRIMARY KEY,
  half_life_days integer NOT NULL,
  prior_mean numeric(3,2) NOT NULL,
  prior_weight numeric(6,2) NOT NULL,
  active boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS reputation_snapshots (
  id bigserial PRIMARY KEY,
  vendor_id uuid NOT NULL REFERENCES vendors(id) ON DELETE CASCADE,
  policy_id text NOT NULL REFERENCES reputation_policies(id),
  score numeric(5,3),
  evidence_count integer NOT NULL DEFAULT 0,
  effective_weight numeric(10,4) NOT NULL DEFAULT 0,
  confidence numeric(5,4) NOT NULL DEFAULT 0,
  computed_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO reputation_policies(id, half_life_days, prior_mean, prior_weight, active)
VALUES ('temporal-bayes-v1', 365, 3.5, 3, true)
ON CONFLICT (id) DO NOTHING;
''', encoding='utf-8')

(BASE / 'docs' / 'API_V1.md').write_text('''# API v1

Read API:
- GET /v1/vendors
- GET /v1/vendors/{id}
- GET /v1/vendors/{id}/evidence
- GET /v1/vendors/{id}/reputation
- GET /v1/search?q=...

Review/admin API:
- POST /v1/evidence
- POST /v1/vendor-candidates
- POST /v1/review-queue/{id}/approve
- POST /v1/review-queue/{id}/reject
''', encoding='utf-8')

if not (BASE / '.git').exists():
    subprocess.run(['git', 'init', '-b', 'main', str(BASE)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    subprocess.run(['git', '-C', str(BASE), 'config', 'user.name', 'Sunlake'], check=True)
    subprocess.run(['git', '-C', str(BASE), 'config', 'user.email', 'register@milkcat.org'], check=True)
subprocess.run(['git', '-C', str(BASE), 'add', '.'], check=True)
if subprocess.run(['git', '-C', str(BASE), 'diff', '--cached', '--quiet']).returncode != 0:
    subprocess.run(['git', '-C', str(BASE), 'commit', '-m', 'bootstrap: vendor reputation domain service'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

gh = shutil.which('gh') or '/usr/bin/gh'
gh_exists = Path(gh).exists()
gh_auth_ok = False
gh_user = None
repo_created = False
repo_url = None
repo_error = None
if gh_exists:
    p = subprocess.run([gh, 'auth', 'status'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15)
    gh_auth_ok = p.returncode == 0
if gh_auth_ok:
    q = subprocess.run([gh, 'api', 'user', '--jq', '.login'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15)
    if q.returncode == 0:
        gh_user = q.stdout.strip() or None
    view = subprocess.run([gh, 'repo', 'view', 'alston-personal/vendor-reputation-service', '--json', 'url', '--jq', '.url'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=20)
    if view.returncode == 0:
        repo_url = view.stdout.strip() or None
    else:
        create = subprocess.run([gh, 'repo', 'create', 'alston-personal/vendor-reputation-service', '--private', '--source', str(BASE), '--remote', 'origin', '--push'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
        repo_created = create.returncode == 0
        if repo_created:
            view = subprocess.run([gh, 'repo', 'view', 'alston-personal/vendor-reputation-service', '--json', 'url', '--jq', '.url'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=20)
            if view.returncode == 0:
                repo_url = view.stdout.strip() or None
        else:
            repo_error = (create.stderr or create.stdout).strip()[:300]

print(json.dumps({
    'schema': 'milkcat.vendor-service-bootstrap/v1',
    'oracle_path': str(BASE),
    'git_initialized': (BASE / '.git').exists(),
    'gh_installed': gh_exists,
    'gh_auth_ok': gh_auth_ok,
    'gh_user': gh_user,
    'repo_created': repo_created,
    'repo_url': repo_url,
    'repo_error': repo_error,
    'core_modified': False,
    'domain_schema_written': True,
    'api_spec_written': True,
}, ensure_ascii=False, indent=2))
