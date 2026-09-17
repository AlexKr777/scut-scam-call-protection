"""Show environment-only AnyModel setup; never accept or persist a key."""


def main() -> int:
    print("Configure AnyModel as Windows user environment variables; SCUT never stores the API key.")
    print('SETX SCUT_AI_PROVIDER "anymodel"')
    print('SETX SCUT_AI_BASE_URL "https://anymodel.org/v1"')
    print('SETX SCUT_AI_MODEL "kmc/k3"')
    print('SETX SCUT_AI_API_KEY "<your-secret>"')
    print("Restart Codex/VS Code or the SCUT process after SETX, then run scripts/semantic_provider_smoke.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
