---
tür: rehber
kategori: sistem
tags:
- sistem
- MAKE-md
üst-sayfa: '[[_Sistem/_Sistem|Sistem]]'
ana-sayfa: '[[Vault|Ana Sayfa]]'
---

# MAKE.md Kullanım Rehberi

## Yapının mantığı

Her ana klasör bir **Space**, klasörle aynı adı taşıyan not ise o Space'in ana sayfasıdır. Notların ortak özellikleri YAML/frontmatter içinde tutulur. Böylece içerikler normal Markdown olarak kalırken MAKE.md Context içinde tablo, liste, pano, takvim veya galeri görünümüne alınabilir.

## İlk açılışta yapılacaklar

1. Kasayı Obsidian ile aç ve MAKE.md indekslemesinin tamamlanmasını bekle.
2. Sol taraftaki MAKE.md gezgininden bir alanı aç.
3. Alanın **Context** bölümünde mevcut frontmatter özelliklerini içe aktar. Sürümüne göre düğme adı **Import properties**, **Existing properties** veya **Add property** altında görünebilir.
4. Aşağıdaki önerilen görünümü kaydet.

| Alan | Önerilen görünüm | Gösterilecek özellikler |
|---|---|---|
| Kişiler | Galeri + Tablo | ilişki, kategori, konum, durum, kapak |
| Yerler | Galeri + Tablo | kategori, konum, durum, kapak |
| İş | Tablo | kategori, alan, durum |
| Teknoloji | Tablo | kategori, teknoloji, durum |
| Rutinler | Pano veya Tablo | kategori, saat, vardiya, durum |

## Yeni not oluşturma

İlgili Space içinde **New from Template** komutunu kullan. Her alanın `.space/templates` klasörüne uygun şablon yerleştirildi. Obsidian'ın kendi Şablonlar eklentisi için aynı dosyalar `_Sistem/Şablonlar` klasöründe de bulunur.

## Özellik kuralları

- `tür`: notun ana nesne tipi; örneğin `kişi`, `yer`, `iş-referansı`.
- `kategori`: aynı tür içindeki alt grup.
- `durum`: `aktif`, `beklemede`, `tamamlandı`, `arşiv` veya `eksik`.
- `tags`: arama ve etiket alanları için kısa sınıflandırmalar.
- `konum`: Google Maps bağlantısı.
- `kapak`: kişi/yer galerisi için görsel bağlantısı veya kasa içi ek dosya.

## Temizlik ilkesi

Yeni bir konu için hemen yeni klasör açma. Önce mevcut Space içinde `tür` ve `kategori` ile sınıflandır. Yalnızca içerik sayısı ve kullanım şekli belirgin biçimde ayrıştığında yeni Space oluştur.

<!-- ATOMIK-RELATIONS:START -->
> [!abstract] Bağlantılar
> [[_Sistem/_Sistem|Sistem]] · [[Vault|Ana Sayfa]]
<!-- ATOMIK-RELATIONS:END -->
