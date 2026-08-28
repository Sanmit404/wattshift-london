# GitHub Upload Guide — WattShift London

This guide publishes the project without committing the roughly 10 GB raw
dataset, local Python environments, interrupted downloads, or macOS metadata.

## Recommended repository settings

| Setting | Recommendation |
|---|---|
| Repository name | `wattshift-london` |
| Description | Causal analysis of how dynamic electricity prices changed household demand in the Low Carbon London smart-meter trial. |
| Default branch | `main` |
| Visibility | Start private if you are still reviewing; switch to public when the checklist below is complete |
| README | Do not initialise one on GitHub; this project already includes `README.md` |
| .gitignore | Do not add another one on GitHub; this project already includes it |
| Licence | Choose deliberately before public release; MIT is common for reusable analysis code |

Recommended GitHub topics:

```text
causal-inference
difference-in-differences
dynamic-pricing
smart-meter
energy-economics
duckdb
panel-data
python
london
data-analysis
```

## Pre-upload checklist

From the project folder, confirm that:

- `README.md` renders locally and every `outputs/*.png` image exists.
- `outputs/summary.txt` agrees with the headline README results.
- `data/`, `.venv/`, `__pycache__/`, `.DS_Store`, `*.part`, and logs are
  ignored.
- no access tokens, passwords, cookies, private keys, email dumps, or local
  configuration files are present.
- the committed outputs are small enough for normal GitHub storage. The largest
  current file is `outputs/halfhour_2013_wide.csv`, about 1.5 MB.
- you have chosen whether the repository should be private or public.
- you have chosen a software licence before public reuse. The source dataset has
  its own Creative Commons Attribution terms; a code licence does not replace
  the dataset's licence.

Useful local checks:

```bash
cd "/Users/sanmitsarkar/Documents/DAproject"

git status --short
git check-ignore data/ .venv/ .DS_Store
find . -type f -size +90M -not -path "./.git/*"
```

The last command should print nothing.

## First upload with Git

### 1. Create an empty GitHub repository

1. Sign in to GitHub.
2. Select **New repository**.
3. Use `wattshift-london` as the repository name.
4. Choose **Private** while reviewing or **Public** when ready to showcase it.
5. Do **not** add a README, `.gitignore`, or licence during repository creation.
6. Create the repository and copy its HTTPS URL.

### 2. Initialise and review locally

```bash
cd "/Users/sanmitsarkar/Documents/DAproject"

git init -b main
git add .
git status
```

Review the staged list carefully. It should contain the Python scripts, README,
this guide, requirements, `.gitignore`, and `outputs/`. It should not contain
`data/`, `.venv/`, `.DS_Store`, or temporary files.

### 3. Commit

```bash
git commit -m "Publish WattShift London analysis"
```

### 4. Connect and push

The connected GitHub account is `Sanmit404`. Replace it only if you intend to
publish under a different account.

```bash
git remote add origin https://github.com/Sanmit404/wattshift-london.git
git push -u origin main
```

If GitHub asks for credentials over HTTPS, use a personal access token or an
authorised credential manager rather than an account password.

## Upload through the GitHub website

The website upload is suitable for this repository because every tracked file is
well below GitHub's individual-file limit:

1. Create the empty repository.
2. Select **uploading an existing file**.
3. Drag in the project files and `outputs/` folder.
4. Confirm `data/`, `.venv/`, and `.DS_Store` are absent.
5. Commit directly to `main`.

Git is preferred because it preserves a clean local history and makes later
updates easier.

## After the first upload

1. Open the repository homepage and confirm all six figures render in the README.
2. Open `outputs/summary.txt` and `outputs/did_overall.csv` to verify that
   result files are downloadable.
3. Add the recommended description and topics under **About**.
4. Add a software licence if the repository is public.
5. Enable Issues only if you want questions or contributions.
6. Add branch protection later if other people begin contributing.
7. Cite and link the official London Datastore dataset rather than uploading the
   raw source data.

## Updating the repository

```bash
cd "/Users/sanmitsarkar/Documents/DAproject"

git status
git add README.md GITHUB_UPLOAD_GUIDE.md .gitignore plots.py outputs/
git commit -m "Update analysis documentation and outputs"
git push
```

Always inspect `git status` before committing. Do not use `git add -f data/`;
the data exclusion is intentional.

## If a remote or repository already exists

Inspect it first:

```bash
git remote -v
git branch --show-current
```

To correct only the URL:

```bash
git remote set-url origin https://github.com/Sanmit404/wattshift-london.git
```

Do not force-push unless you understand exactly which remote history would be
replaced.

## Large-data policy

- Keep `data/raw/` and `data/interim/` out of Git.
- Let `download_data.py` retrieve the authoritative public source.
- Keep compact, reviewable result tables and figures under `outputs/`.
- Use GitHub Releases or an external research-data archive for any future large
  derived artifact that genuinely needs distribution.
- Use Git LFS only when collaborators must version a large derived file; it is
  unnecessary for the current repository.

## Public-release checklist

Before switching from private to public:

- choose and add a software licence;
- retain the dataset attribution and source links;
- confirm that all household identifiers remain pseudonymous;
- confirm there are no secrets or local-only files in Git history;
- verify the results from a clean environment when practical; and
- make clear that this is an independent analysis, not an official UK Power
  Networks or Greater London Authority result.
