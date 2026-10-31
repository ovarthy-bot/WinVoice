# 👤 Kişisel

Kişisel notlar klasörle değil, `#sosyal` ve alt etiketleriyle bulunur.

```dataview
TABLE file.tags AS "Etiketler", file.mtime AS "Güncelleme"
FROM #sosyal
WHERE file.name != "Kişisel"
SORT file.mtime DESC
```
