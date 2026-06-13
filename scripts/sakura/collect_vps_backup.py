import os
import subprocess


ROOT = "/home/ubuntu/boatrace"


def print_file_contents() -> None:
    print("### FILE_CONTENTS_BEGIN ###")
    if os.path.isdir(ROOT):
        for dirpath, _, filenames in os.walk(ROOT):
            filenames.sort()
            for name in filenames:
                path = os.path.join(dirpath, name)
                print(f"\n===== FILE: {path} =====")
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as handle:
                        for index, line in enumerate(handle, 1):
                            if index > 400:
                                print("\n[TRUNCATED_AFTER_400_LINES]")
                                break
                            print(line, end="")
                except Exception as error:
                    print(f"[READ_ERROR] {error}")
    else:
        print(f"MISSING:{ROOT}")
    print("\n### FILE_CONTENTS_END ###")


def print_systemd_defs() -> None:
    print("### SYSTEMD_DEFS_BEGIN ###")
    try:
        result = subprocess.run(
            "systemctl list-unit-files --type=service --no-legend --no-pager | awk '{print $1}' | grep -i boatrace || true",
            shell=True,
            check=False,
            capture_output=True,
            text=True,
        )
        services = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        for service in services:
            print(f"\n===== SERVICE: {service} =====")
            cat = subprocess.run(
                ["systemctl", "cat", service],
                check=False,
                capture_output=True,
                text=True,
            )
            output = cat.stdout or cat.stderr
            print(output, end="" if output.endswith("\n") else "\n")
    except Exception as error:
        print(f"[SYSTEMD_ERROR] {error}")
    print("\n### SYSTEMD_DEFS_END ###")


if __name__ == "__main__":
    print_file_contents()
    print_systemd_defs()