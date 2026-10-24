#!/usr/bin/env python3
"""Attrappe für `docker` in den CLI-Tests (core/test_docker_install.py).

Zustand liegt in $FAKE_DOCKER_STATE (JSON):
  images          {Image-Name: Image-ID}  aktueller lokaler Stand
  remote          {Image-Name: Image-ID}  Stand in der Registry (pull holt ihn)
  fail_up_ids     [Image-ID, …]           `compose up` scheitert, solange eine
                                           dieser IDs in Benutzung ist
  running         {Image-Name: Image-ID}  womit die Container gerade laufen
                                           (Standard: wie images; `up` setzt es)
Jeder Aufruf wird als JSON-Zeile in $FAKE_DOCKER_STATE.calls protokolliert.
"""
import json
import os
import re
import sys

STATE = os.environ["FAKE_DOCKER_STATE"]


def load():
    with open(STATE, encoding="utf-8") as handle:
        return json.load(handle)


def save(state):
    with open(STATE, "w", encoding="utf-8") as handle:
        json.dump(state, handle)


def compose_images(version):
    """Image-Namen wie in compose.yml (vereinfacht auf die drei eigenen)."""
    registry = os.environ.get("WACHBUCH_REGISTRY") or env_value("WACHBUCH_REGISTRY") or "ghcr.io/katschko-it"
    return [f"{registry}/rettungswache-wachbuch{suffix}:{version}" for suffix in ("", "-backup", "-db")]


def env_value(key):
    """Letzter Wert von KEY aus ./.env (wie env_get in der CLI)."""
    value = ""
    try:
        with open(".env", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith(key + "="):
                    value = line.split("=", 1)[1].strip()
    except OSError:
        pass
    return value


def main(argv):
    with open(STATE + ".calls", "a", encoding="utf-8") as log:
        log.write(json.dumps(argv) + "\n")
    state = load()
    version = env_value("WACHBUCH_VERSION") or "latest"
    if argv[:1] == ["compose"]:
        args = argv[1:]
        command = args[0] if args else ""
        if command == "ps":
            if "-q" in args:
                for name in compose_images(version):
                    print("container:" + name)
            return 0
        if command == "config" and "--images" in args:
            print("\n".join(compose_images(version)))
            return 0
        if command == "pull":
            if state.get("pull_fails"):
                return 1
            for name in compose_images(version):
                if name in state.get("remote", {}):
                    state["images"][name] = state["remote"][name]
            save(state)
            return 0
        if command == "up":
            used = {state["images"].get(name) for name in compose_images(version)}
            if used & set(state.get("fail_up_ids", [])):
                return 1
            state["running"] = {name: state["images"].get(name) for name in compose_images(version)}
            save(state)
            return 0
        if command == "exec" and "once" in args:
            print("Dump erstellt")
            print("BACKUP_FILE=/backups/rwsth-test.dump")
            return 0
        if command == "cp":
            target = args[-1]
            os.makedirs(target, exist_ok=True)
            open(os.path.join(target, "rwsth-test.dump"), "w").close()
            return 0
        return 0
    if argv[:1] == ["inspect"] and argv[-1].startswith("container:"):
        name = argv[-1].split(":", 1)[1]
        if "{{.Config.Image}}" in argv:
            print(name)
        else:
            print(state.get("running", state["images"]).get(name, ""))
        return 0
    if argv[:2] == ["image", "inspect"]:
        name = argv[-1]
        image_id = state["images"].get(name)
        if image_id is None:
            return 1
        print(image_id)
        return 0
    if argv[:1] == ["tag"]:
        source, target = argv[1], argv[2]
        if re.match(r"^sha256:", source):
            # Wie der containerd-Image-Speicher (Docker 29): Ein Image ohne
            # Namen ist über seine ID nicht mehr erreichbar.
            if source not in state["images"].values():
                print(f"Error response from daemon: No such image: {source}", file=sys.stderr)
                return 1
            state["images"][target] = source
        else:
            if source not in state["images"]:
                return 1
            state["images"][target] = state["images"][source]
        save(state)
        return 0
    if argv[:2] == ["image", "rm"]:
        for name in argv[2:]:
            state["images"].pop(name, None)
        save(state)
        return 0
    if argv[:2] == ["image", "prune"]:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
