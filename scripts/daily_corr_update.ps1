$ErrorActionPreference = "Stop"
Set-Location "$HOME\repo-solana"
git pull origin main
python scripts\update_correlations.py --xlsx "$HOME\Desktop\Solana_Matriz_Exposicao_Risco_v2.xlsx" --json frontend\assets\corr_matrices.json --period 2y --interval 1wk
git add frontend/assets/corr_matrices.json
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
  git commit -m "chore(data): daily refresh corr_matrices.json"
  git push origin main
}