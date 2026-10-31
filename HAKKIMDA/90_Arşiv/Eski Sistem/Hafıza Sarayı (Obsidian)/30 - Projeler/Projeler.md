# 🛠️ Projeler

Her proje için bir ana not oluştur ve `#proje` ile `#durum/aktif` etiketlerini ekle.

```dataview
TABLE file.tags AS "Etiketler", file.mtime AS "Güncelleme"
FROM #proje
WHERE file.name != "Projeler"
SORT file.mtime DESC
```
