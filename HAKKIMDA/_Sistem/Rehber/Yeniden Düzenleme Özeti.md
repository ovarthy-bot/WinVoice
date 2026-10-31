---
tür: kayıt
kategori: sistem
tags:
- sistem
- taşıma
üst-sayfa: '[[_Sistem/_Sistem|Sistem]]'
ana-sayfa: '[[Vault|Ana Sayfa]]'
---

# Yeniden Düzenleme Özeti

## Yeni alanlar

- `00_Gelen_Kutusu`: henüz sınıflandırılmamış içerikler
- `10_Kişiler`: kişiler ve kişi listeleri
- `20_Yerler`: konumlar
- `30_İş`: uçak bakım ve hat mekanik referansları
- `40_Teknoloji`: yazılım ve teknoloji notları
- `50_Rutinler`: tekrar eden iş ve servis bilgileri
- `90_Arşiv`: eski sistem ve kullanılmayan içerikler
- `_Sistem`: şablonlar, ekler ve rehberler

## Başlıca taşımalar

| Eski yol | Yeni yol |
|---|---|
| `00_Gelen_kutusu/Hatırlamayı istediğim şeyler.md` | `00_Gelen_Kutusu/Öğrenilecek Kavramlar.md` |
| `01_Kişiler/Anneannem in evi.md` | `10_Kişiler/Nurten Yüksel.md` |
| `01_Kişiler/Teyzem.md` | `10_Kişiler/Birsen Duran.md` |
| `01_Kişiler/Hat mekanik yöneticileri.md` | `30_İş/Hat Mekanik Yöneticileri.md` |
| `02_Yerler/*` | `20_Yerler/*` |
| `03_Referanslar/Flutter Derleme ve Yayınlama Komutları.md` | `40_Teknoloji/Flutter Derleme ve Yayınlama Komutları.md` |
| `03_Referanslar/Çatalca iga servisi.md` | `50_Rutinler/Çatalca İGA Servisi.md` |

## Uygulanan düzeltmeler

- Rastgele oluşturulmuş `campo_1785607206518` alanı, anlaşılır `kategori: su-alma-noktası` alanına dönüştürüldü.
- `type`, `etiket` ve `Ev lokasyon` alanları; `tür`, `tags` ve `konum` olarak standartlaştırıldı.
- Kişi ve referans listeleri Markdown tablolarına çevrildi.
- APK üretme komutu `flutter build apk` olarak düzeltildi.
- Eski Bases/Notion dosyaları silinmedi; `90_Arşiv/Eski Sistem` içine alındı.
- Eski MAKE.md önbellekleri ve çalışma alanı düzenleri aktif kasaya taşınmadı; eklenti ve Obsidian bunları yeni dosya yollarına göre yeniden oluşturacaktır.

<!-- ATOMIK-RELATIONS:START -->
> [!abstract] Bağlantılar
> [[_Sistem/_Sistem|Sistem]] · [[Vault|Ana Sayfa]]
<!-- ATOMIK-RELATIONS:END -->
