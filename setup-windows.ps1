# D&D Scribe - Windows Setup Script
# Run this in PowerShell after cloning the repo

Write-Host "D&D Scribe - Windows Setup" -ForegroundColor Cyan
Write-Host "==========================`n" -ForegroundColor Cyan

# Check Python
Write-Host "Checking Python..." -ForegroundColor Yellow
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host "ERROR: Python not found. Install from Microsoft Store or python.org" -ForegroundColor Red
    exit 1
}
$pythonVersion = python --version
Write-Host "  Found: $pythonVersion" -ForegroundColor Green

# Check ffmpeg
Write-Host "Checking ffmpeg..." -ForegroundColor Yellow
$ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
if (-not $ffmpeg) {
    Write-Host "  ffmpeg not found. Installing via winget..." -ForegroundColor Yellow
    winget install ffmpeg
    Write-Host "  Please restart your terminal after installation" -ForegroundColor Yellow
} else {
    Write-Host "  Found: ffmpeg" -ForegroundColor Green
}

# Create virtual environment
Write-Host "`nCreating virtual environment..." -ForegroundColor Yellow
if (Test-Path "venv") {
    Write-Host "  venv already exists, skipping" -ForegroundColor Gray
} else {
    python -m venv venv
    Write-Host "  Created venv" -ForegroundColor Green
}

# Activate venv
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
& .\venv\Scripts\Activate.ps1

# Install PyTorch with CUDA
Write-Host "`nInstalling PyTorch with CUDA 12.1 support..." -ForegroundColor Yellow
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# Check CUDA
Write-Host "`nChecking CUDA availability..." -ForegroundColor Yellow
$cudaCheck = python -c "import torch; print('CUDA:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'None')"
Write-Host $cudaCheck -ForegroundColor Cyan

# Install other dependencies
Write-Host "`nInstalling remaining dependencies..." -ForegroundColor Yellow
pip install -r requirements.txt

# Check for .env
if (-not (Test-Path ".env")) {
    Write-Host "`nCreating .env file..." -ForegroundColor Yellow
    "HUGGINGFACE_TOKEN=your_token_here" | Out-File -FilePath ".env" -Encoding utf8
    Write-Host "  Created .env - Please add your HuggingFace token!" -ForegroundColor Yellow
}

# Update config for GPU
Write-Host "`nUpdating config.yaml for GPU..." -ForegroundColor Yellow
$config = Get-Content "config.yaml" -Raw
$config = $config -replace "device: cpu", "device: cuda"
$config = $config -replace "compute_type: int8", "compute_type: float16"
$config = $config -replace "model: medium", "model: large-v3"
$config | Out-File -FilePath "config.yaml" -Encoding utf8
Write-Host "  Updated to: device=cuda, compute_type=float16, model=large-v3" -ForegroundColor Green

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "Setup complete!" -ForegroundColor Green
Write-Host "`nNext steps:" -ForegroundColor Yellow
Write-Host "1. Add your HuggingFace token to .env" -ForegroundColor White
Write-Host "2. Accept pyannote licenses on HuggingFace" -ForegroundColor White
Write-Host "3. Run: python scribe.py process <audio_file>" -ForegroundColor White
Write-Host "========================================`n" -ForegroundColor Cyan
