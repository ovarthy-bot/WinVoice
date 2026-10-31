# 🏷️ Etiket Rehberi

Bu kasa etiketlerle yönetilir. Klasör, notu saklar; etiket, notu buldurur.

## Bir not için basit formül

`1 ana alan + en fazla 2 bağlam etiketi + 1 durum`

Örnekler:

- A330 motor hidrolik ikmali: `#iş #iş/bakım #iş/havacılık #durum/aktif`
- MEL ile sefere verme notu: `#iş #iş/prosedür #durum/aktif`
- İngilizce kelime notu: `#sosyal #sosyal/öğrenme #durum/tekrar`
- Kilo alma uygulaması: `#proje #proje/yazılım #durum/aktif`

## Kullanılacak etiketler

| Grup | Etiketler |
|---|---|
| Ana alan | `#iş`, `#sosyal`, `#proje` |
| İş ve havacılık | `#iş/havacılık`, `#iş/bakım`, `#iş/prosedür`, `#iş/yetki`, `#iş/ojt`, `#iş/ders`, `#iş/terim`, `#iş/taslak`, `#iş/iletişim`, `#iş/saat`, `#iş/telefon` |
| Kişisel | `#sosyal/sağlık`, `#sosyal/öğrenme`, `#sosyal/finans`, `#sosyal/ev`, `#sosyal/hafıza`, `#sosyal/takip`, `#sosyal/fiyat`, `#sosyal/tarih` |
| Proje | `#proje/yazılım`, `#proje/ev`, `#proje/kişisel` |
| Not türü | `#tür/referans`, `#tür/prosedür`, `#tür/öğrenme`, `#tür/kayıt`, `#tür/kısayol` |
| Durum | `#durum/aktif`, `#durum/taslak`, `#durum/tekrar`, `#durum/beklemede`, `#durum/arşiv` |

## Etiket ekleme

Notun en üstündeki `tags:` alanına etiketi `#` işareti olmadan yaz.

```yaml
tags:
  - iş
  - iş/prosedür
  - tür/prosedür
  - durum/aktif
```

Arama kutusuna `tag:#iş/prosedür` yazarak o konudaki tüm notları bulabilirsin.
