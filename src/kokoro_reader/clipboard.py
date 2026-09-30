import subprocess


def read_selection(run=subprocess.run):
    errors = []
    for primary in (True, False):
        args = ["wl-paste", "--no-newline", "--type", "text"]
        if primary:
            args.append("--primary")
        try:
            result = run(args, capture_output=True, text=True, timeout=3, check=False)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout
            if result.returncode:
                errors.append(result.stderr.strip())
        except subprocess.TimeoutExpired:
            errors.append("Tempo esgotado ao consultar Wayland")
        except FileNotFoundError as exc:
            raise RuntimeError("Instale wl-clipboard") from exc
    if len(errors) == 2:
        raise RuntimeError("Seleção/clipboard indisponíveis: " + "; ".join(errors))
    return ""
