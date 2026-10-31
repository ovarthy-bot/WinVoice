# vault_audit.py
#
# HAKKIMDA Obsidian kasasının YALNIZCA OKUMA amaçlı sağlık denetimi.
#
# Bilinçli olarak vault_knowledge.py / personal_context.py'den HİÇBİR ŞEY
# import etmez ve hiçbir dosyayı değiştirmez/silmez — amaç, WinVoice'un şu an
# sağlıklı çalışan RAG/hatırlatma sistemine sıfır risk taşımak. Bu betik
# tamamen bağımsız bir araçtır; sadece bir rapor yazdırır.
#
# Çalıştırmak için:  python vault_audit.py
#
# Tespit ettiği şeyler:
#   1. Kopuk notlar      — hiçbir nottan link almayan VE hiçbir nota link
#                          vermeyen (vault'un bağlantı grafiğinden tamamen
#                          ayrık) notlar.
#   2. Kırık linkler     — [[...]] ile var olmayan bir nota işaret eden
#                          bağlantılar.
#   3. Aynı isimli notlar — farklı klasörlerde aynı dosya adına sahip,
#                          Obsidian'ın link çözümlemesini belirsizleştirebilecek
#                          notlar.
#   4. İndekse geri bağlantısı olmayan notlar — numaralı bir üst klasördeyken
#                          (10_Kişiler, 50_Rutinler vb.) o klasörün kendi
#                          indeks notuna (ör. 10_Kişiler.md) hiç link vermeyen
#                          notlar.
#   5. İndekste anılıp dosyası bulunamayan kayıtlar — bir indeks notunun
#                          işaret ettiği ama artık var olmayan (silinmiş/
#                          yeniden adlandırılmış) notlar.
#   6. Dosyası var ama indekste anılmayan notlar — klasörde fiziksel olarak
#                          duran ama kendi indeks notunun listesine hiç
#                          eklenmemiş notlar (ör. daha önce 50_Rutinler.md'de
#                          görülen Şifrelerim.md/Dahili Nolar.md eksikliği).

import os
import re
from collections import defaultdict

VAULT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "HAKKIMDA")

# Obsidian/MakeMD'nin kendi iç/ayar klasörleri — kişisel içerik değil,
# kasa yapılandırmasıdır; denetime dahil edilmez.
_EXCLUDE_DIR_NAMES = {".obsidian", ".space", ".makemd", ".trash", "_Sistem"}

_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
_NUMBERED_FOLDER_RE = re.compile(r"^\d{2}_")


def _iter_files():
    for root, dirs, files in os.walk(VAULT_DIR):
        dirs[:] = [d for d in dirs if d not in _EXCLUDE_DIR_NAMES]
        for fn in files:
            if not fn.lower().endswith(".md"):
                continue
            if "sync-conflict" in fn.lower():
                continue
            yield os.path.join(root, fn)


def _top_folder(folder):
    return folder.split(os.sep)[0]


def _load_notes():
    """Her not için {path, folder, top_folder, name, links} döner.
    `links`, notun içindeki TÜM [[...]] bağlantılarının ham hedef isimleridir
    (vault_knowledge.py'nin aksine burada link sözdizimi temizlenmez —
    denetim için ham bağlantı bilgisine ihtiyaç var)."""
    notes = []
    for path in _iter_files():
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read()
        except Exception:
            continue
        rel = os.path.relpath(path, VAULT_DIR)
        folder = os.path.dirname(rel) or "."
        name = os.path.splitext(os.path.basename(path))[0]
        links = [m.group(1).strip() for m in _WIKILINK_RE.finditer(raw)]
        notes.append({
            "path": rel,
            "folder": folder,
            "top_folder": _top_folder(folder),
            "name": name,
            "links": links,
        })
    return notes


def _build_indices(notes):
    """İki eşleme döner: isim (küçük harf, uzantısız) -> not, ve tam yol
    (küçük harf, uzantısız, "/" ile normalize) -> not. Obsidian [[Not Adı]]
    bağlantılarını basit isimle çözümleyebildiği gibi [[Klasör/Not Adı]]
    şeklinde yol öneki de kabul eder; ikisi de desteklenmeli."""
    by_name = {}
    by_full_path = {}
    duplicates = []
    for note in notes:
        key = note["name"].lower()
        if key in by_name:
            duplicates.append((by_name[key]["path"], note["path"]))
        else:
            by_name[key] = note
        path_no_ext = os.path.splitext(note["path"])[0].replace(os.sep, "/").lower()
        by_full_path[path_no_ext] = note
    return by_name, by_full_path, duplicates


# Bir not içindeki [[...]] eşleşmesi, gerçek bir bağlantı değil de örnek/
# açıklama metni olabilir (ör. "Obsidian benzeri `[[Not Adı]]` syntax
# desteklenmelidir" gibi bir özellik taslağı). Böyle durumlarda hedef metni
# alışılmadık uzun olur veya ters tırnak/satır sonu içerir — bunlar temiz
# "kırık link" listesini kirletmesin diye ayrı say.
_SUSPICIOUS_TARGET_RE = re.compile(r"[`\n]")
_MAX_PLAUSIBLE_TARGET_LEN = 80


def _resolve_target(target_name, by_name, by_full_path):
    normalized = target_name.replace("\\", "/").lower()
    if "/" in normalized:
        hit = by_full_path.get(normalized)
        if hit is not None:
            return hit
        bare = normalized.rsplit("/", 1)[-1]
        return by_name.get(bare)
    return by_name.get(normalized)


def _looks_like_real_link_target(target_name):
    return (
        len(target_name) <= _MAX_PLAUSIBLE_TARGET_LEN
        and not _SUSPICIOUS_TARGET_RE.search(target_name)
    )


def audit():
    notes = _load_notes()
    by_name, by_full_path, duplicate_names = _build_indices(notes)

    incoming = defaultdict(set)
    outgoing = defaultdict(set)
    broken_links = []
    suspicious_link_syntax = []

    for note in notes:
        for target_name in note["links"]:
            if not _looks_like_real_link_target(target_name):
                suspicious_link_syntax.append((note["path"], target_name))
                continue
            target = _resolve_target(target_name, by_name, by_full_path)
            if target is None:
                broken_links.append((note["path"], target_name))
                continue
            if target["path"] == note["path"]:
                continue
            outgoing[note["path"]].add(target["path"])
            incoming[target["path"]].add(note["path"])

    orphan_notes = sorted(
        n["path"] for n in notes
        if not outgoing[n["path"]] and not incoming[n["path"]]
    )

    index_notes = [n for n in notes if n["name"] == n["top_folder"]]
    index_by_folder = {n["top_folder"]: n for n in index_notes}

    missing_index_backlink = []
    for n in notes:
        if not _NUMBERED_FOLDER_RE.match(n["top_folder"]):
            continue
        if n["name"] == n["top_folder"]:
            continue  # bu notun kendisi o klasörün indeksi
        folder_index = index_by_folder.get(n["top_folder"])
        if folder_index is None:
            continue
        if folder_index["path"] not in outgoing[n["path"]]:
            missing_index_backlink.append(n["path"])
    missing_index_backlink.sort()

    dangling_in_index = []
    for idx in index_notes:
        for target_name in idx["links"]:
            if not _looks_like_real_link_target(target_name):
                continue
            if _resolve_target(target_name, by_name, by_full_path) is None:
                dangling_in_index.append((idx["path"], target_name))

    notes_by_top_folder = defaultdict(list)
    for n in notes:
        notes_by_top_folder[n["top_folder"]].append(n)

    missing_from_index = []
    for idx in index_notes:
        linked_lower = {t.lower() for t in idx["links"]}
        for n in notes_by_top_folder.get(idx["top_folder"], []):
            if n["path"] == idx["path"]:
                continue
            if n["name"].lower() not in linked_lower:
                missing_from_index.append((idx["path"], n["path"]))

    # Kök dizinde (hiçbir numaralı kategori klasörünün içinde değil) duran,
    # "Vault.md" (ana giriş sayfası) dışındaki notlar — hiç dosyalanmamış,
    # kategorisiz içerik demektir.
    uncategorized_root_notes = sorted(
        n["path"] for n in notes
        if n["top_folder"] == "." and n["name"].lower() != "vault"
    )

    _print_report(
        total=len(notes),
        orphan_notes=orphan_notes,
        broken_links=broken_links,
        suspicious_link_syntax=suspicious_link_syntax,
        duplicate_names=duplicate_names,
        missing_index_backlink=missing_index_backlink,
        dangling_in_index=dangling_in_index,
        missing_from_index=missing_from_index,
        uncategorized_root_notes=uncategorized_root_notes,
    )


def _print_report(total, orphan_notes, broken_links, suspicious_link_syntax,
                   duplicate_names, missing_index_backlink, dangling_in_index,
                   missing_from_index, uncategorized_root_notes):
    print("=" * 70)
    print(f"HAKKIMDA Vault Denetimi — toplam {total} not tarandı")
    print("=" * 70)

    print(f"\n[1] Kopuk notlar (hiç giriş/çıkış bağlantısı yok) — {len(orphan_notes)}")
    for p in orphan_notes:
        print(f"  - {p}")

    print(f"\n[2] Kırık linkler (var olmayan bir nota işaret ediyor) — {len(broken_links)}")
    for src, target in broken_links:
        print(f"  - {src}  ->  [[{target}]] (hedef bulunamadı)")

    print(f"\n[3] Aynı isimli birden fazla not — {len(duplicate_names)}")
    for first, second in duplicate_names:
        print(f"  - {first}  <->  {second}")

    print(f"\n[4] Kendi klasör indeksine geri bağlantısı olmayan notlar — {len(missing_index_backlink)}")
    for p in missing_index_backlink:
        print(f"  - {p}")

    print(f"\n[5] İndekste anılıp dosyası bulunamayan kayıtlar — {len(dangling_in_index)}")
    for idx, target in dangling_in_index:
        print(f"  - {idx} içinde [[{target}]] -> dosya yok")

    print(f"\n[6] Dosyası var ama kendi klasör indeksinde hiç anılmayan notlar — {len(missing_from_index)}")
    for idx, note_path in missing_from_index:
        print(f"  - {note_path}  ({idx} indeksinde yok)")

    print(f"\n[7] Kategori klasörüne dosyalanmamış, kasanın kökünde duran notlar — {len(uncategorized_root_notes)}")
    for p in uncategorized_root_notes:
        print(f"  - {p}")

    print(f"\n[8] Şüpheli/bozuk link söz dizimi (muhtemelen gerçek bir bağlantı değil, "
          f"örnek/açıklama metni) — {len(suspicious_link_syntax)}")
    for src, target in suspicious_link_syntax:
        preview = target[:60].replace("\n", " ") + ("…" if len(target) > 60 else "")
        print(f"  - {src}  içinde: [[{preview}]]")

    print("\nBu rapor salt okunurdur; hiçbir dosya değiştirilmedi/silinmedi.")


if __name__ == "__main__":
    audit()
