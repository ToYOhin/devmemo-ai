param(
  [string]$Model = "deepseek-v4-pro",
  [string]$BaseUrl = "https://api.deepseek.com"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot "ai-service\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
  throw "AI Service virtual environment not found. Create ai-service/.venv first."
}

$previous = @{}
foreach ($name in "AI_PROVIDER", "DEEPSEEK_API_KEY", "DEEPSEEK_MODEL", "DEEPSEEK_BASE_URL") {
  $previous[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}

$secureKey = Read-Host "DeepSeek API key" -AsSecureString
$keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
try {
  $env:AI_PROVIDER = "deepseek"
  $env:DEEPSEEK_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer)
  $env:DEEPSEEK_MODEL = $Model
  $env:DEEPSEEK_BASE_URL = $BaseUrl

  Push-Location (Join-Path $repoRoot "ai-service")
  try {
    @'
import asyncio
import json

from llm import create_provider


async def main() -> None:
    provider = create_provider()
    prompt = (
        "Return exactly one JSON object with fields version, answer, and "
        "citation_refs. Set version to grounded-answer-result-v1 and "
        "citation_refs to [evidence-1]. Use only this synthetic evidence: "
        "evidence-1 says DevMemo AI keeps Memos as source authority."
    )
    result = await provider.generate(prompt)
    payload = json.loads(result.text)
    if set(payload) != {"version", "answer", "citation_refs"}:
        raise RuntimeError("DeepSeek returned an unexpected JSON shape")
    if payload["version"] != "grounded-answer-result-v1":
        raise RuntimeError("DeepSeek returned an unexpected contract version")
    if not isinstance(payload["answer"], str) or not payload["answer"].strip():
        raise RuntimeError("DeepSeek returned an empty answer")
    if payload["citation_refs"] != ["evidence-1"]:
        raise RuntimeError("DeepSeek returned an invalid citation binding")
    print(
        json.dumps(
            {
                "status": "passed",
                "provider": result.provider,
                "version": payload["version"],
                "citation_refs": payload["citation_refs"],
                "answer_chars": len(payload["answer"]),
            },
            separators=(",", ":"),
        )
    )


asyncio.run(main())
'@ | & $python -
    if ($LASTEXITCODE -ne 0) {
      throw "DeepSeek Provider smoke failed with exit code $LASTEXITCODE"
    }
  } finally {
    Pop-Location
  }
} finally {
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer)
  $secureKey.Dispose()
  foreach ($name in $previous.Keys) {
    $value = $previous[$name]
    if ($null -eq $value) {
      Remove-Item "Env:$name" -ErrorAction SilentlyContinue
    } else {
      [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
  }
}
