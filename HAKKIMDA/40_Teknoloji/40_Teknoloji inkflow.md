# inkflow — PDF OCR Süre Tahmin Modülü

#teknoloji #flutter

## Rol ve Görev

Kıdemli bir Flutter geliştirici olarak, hem **Windows** hem de **Android** platformlarında sorunsuz çalışacak bir **PDF İçe Aktarma (Import) ve Dinamik OCR Süre Tahmin Modülü** hazırla.

## Hedef Platformlar

- Windows (Desktop)
- Android (Mobile)

## İş Akışı ve Mantık Kuralları

### 1. Ön Onay Diyaloğu (OCR Taraması)

- PDF dosyası seçildikten veya aktarım tetiklendikten hemen önce kullanıcıya bir iletişim kutusu gösterilsin.
- Soru metni: **"OCR Taraması yapılsın mı?"**
- Seçenekler: **"Evet"** ve **"Hayır"**
- Seçim "Hayır" ise PDF dosyası OCR işlemi yapılmadan doğrudan standart şekilde içe aktarılsın.

### 2. Dinamik Süre Hesaplama ve İlerleme Mantığı (Kullanıcı "Evet" derse)

- OCR işlemi başladığı anda arka planda bir zamanlayıcı (`Stopwatch`) başlatılsın.
- İlerleme oranı **%5** aşamasına geldiğinde:
  - O ana kadar geçen süre (`elapsedTimeAt5Percent`) hafızaya alınsın.
  - Basit orantı mantığı: %1 için geçen süre = elapsedTimeAt5Percent / 5; kalan süre = (elapsedTimeAt5Percent / 5) × (100 − güncel yüzde).
- Yüzdelik oran göstergesinin yanında bu tahmini kalan süre canlı/dinamik olarak formatlanıp yazdırılsın.
- **Arayüz örneği:** `%25 - Tahmini kalan süre: 01:15` veya `%40 (Kalan süre: ~45 sn)`

### 3. Teknik ve Platform Gereksinimleri

- Hem Windows hem de Android ile tam uyumlu dosya seçimi (`file_picker` vb.) ve OCR/PDF işleme mimarisi kurgulanmalı.
- İlerleme durumu ve süre hesaplamaları için UI'ı yormayan, tepkisel bir durum yönetimi (`ValueNotifier`, `Riverpod` veya `Bloc`) kullanılmalı.

## Beklenen Çıktılar

1. **Gerekli bağımlılıklar:** `pubspec.yaml` dosyasına eklenecek Windows ve Android uyumlu paketler.
2. **Hesaplama mantığı (Controller/Service):** %5 aşamasındaki süreyi kaydeden, basit orantı ile kalan süreyi hesaplayan ve saniye/dakika formatına çeviren iş mantığı.
3. **UI bileşenleri:** "OCR Taraması yapılsın mı?" diyalog penceresi; yüzdelik oran + tahmini kalan süreyi bir arada gösteren Progress Bar / Status Widget.
4. **Hata yönetimi:** Dosya okuma hatası, iptal senaryoları ve istisnaların (exception handling) ele alınması.

## İlgili Bağlantılar

- [[40_Teknoloji|Teknoloji]]
- [[İş Kartları düzenleme uygulaması]]
