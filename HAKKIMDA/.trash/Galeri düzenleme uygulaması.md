---
tür: fikir
tags:
  - gelen-kutusu
  - fikir
üst-sayfa: "[[40_Teknoloji]]"
ana-sayfa: "[[Vault|Ana Sayfa]]"
---

# Galeri düzenleme uygulaması

# AI'YA VERİLECEK PROMPT: Akıllı Galeri Düzenleme Uygulaması

## GENEL TANIM

Samsung Galaxy S23 ve sonrası modeller için, **tamamen cihaz üzerinde (on-device) çalışan**, internet bağlantısı gerektirmeyen bir Android galeri düzenleme uygulaması geliştir. Uygulama, kullanıcının fotoğraf galerisini yapay zeka destekli görüntü analizi ve OCR (optik karakter tanıma) kullanarak otomatik olarak kategorize etsin, tekrarlayan/bulanık/kötü fotoğrafları tespit etsin ve metin içeriğine göre akıllı isimlendirme ve arama yapabilsin.

Uygulama özellikle **teknik/endüstriyel kullanım** (bakım kayıtları, iş emirleri, parça etiketleri) ile **günlük kullanım** (ekran görüntüsü, fatura, yemek, evcil hayvan, seyahat fotoğrafları) senaryolarını aynı anda desteklemeli.

---

## HEDEF PLATFORM VE TEKNOLOJİ YIĞINI

- **Platform:** Native Android (Kotlin, Jetpack Compose ile modern UI)
- **Minimum hedef cihaz:** Samsung Galaxy S23 ve sonrası (Snapdragon 8 Gen 2 / Exynos 2200+, NPU/GPU hızlandırmalı ML çıkarımı için yeterli donanım)
- **minSdkVersion:** Android 13 (API 33) öneriliyor; gerekirse API 31'e kadar düşürülebilir
- **ML/AI çerçevesi:**
    - **Google ML Kit** (OCR / Text Recognition v2, on-device)
    - **LiteRT** (eski adıyla TensorFlow Lite) — Image Classification ve Object Detection için
    - **MediaPipe** — görüntü embedding / benzerlik çıkarımı ve gerekiyorsa yüz/nesne tespiti için
    - Gerekirse özel eğitilmiş `.tflite` modelleri (custom LiteRT Object Detection modeli) entegre edilecek şekilde modüler bir ML katmanı tasarla
- **Depolama:** Room (SQLite) — fotoğraf meta verisi, kategori etiketleri, OCR sonuçları, embedding vektörleri ve hash değerleri için yerel veritabanı
- **Arka plan işleme:** WorkManager — galerideki yeni/değişen fotoğrafları arka planda tarayıp analiz etmek için
- **Görüntü işleme:** CameraX/Media3 değil, `MediaStore` API üzerinden galeri erişimi + Coil/Glide ile önizleme yükleme

> Not: Uygulama **tamamen offline** çalışmalı; hiçbir fotoğraf veya metin veri harici bir sunucuya gönderilmemeli (gizlilik açısından kritik, özellikle iş/bakım verileri için).

---

## TEMEL ÖZELLİKLER

### 1. Otomatik Kategorizasyon

Galerideki her fotoğrafı aşağıdaki sınıflardan birine (veya birden fazlasına) otomatik ata:

- Ekran görüntüsü
- Belge
- Fatura
- Yemek
- Ürün
- Evcil hayvan
- Manzara
- (Genişletilebilir: kategori listesi config dosyasından yönetilmeli)

Bunun için:

- **LiteRT Image Classification** modeli (MobileNetV3 veya EfficientNet-Lite tabanlı, gerekirse fine-tune edilmiş) genel sahne sınıflandırması yapsın
- **LiteRT Object Detection** modeli (kahve makinesi, uçak koltuğu, kablo vb. gibi spesifik nesneleri tespit etmek için) nesne bazlı etiketleme yapsın
- Ekran görüntüsü tespiti için hem meta veri (dosya adı, çözünürlük/en-boy oranı, EXIF eksikliği) hem de görsel sınıflandırma birlikte kullanılsın

### 2. ML Kit OCR Entegrasyonu (Metin Tabanlı Arama ve Etiketleme)

- **ML Kit Text Recognition v2** kullanılarak fotoğraflardaki metinler **blok, satır ve kelime seviyesinde** çıkarılsın
- Kullanıcının tanımladığı anahtar kelimeler/desenler (regex destekli) fotoğraf metinlerinde aransın ve eşleşen fotoğraflar otomatik kategorize edilsin
- Aşağıdaki alan türleri özel olarak ayrıştırılsın (parça/iş emri takibi için):
    - **W/O** (Work Order — iş emri numarası)
    - **NRC** (Non-Routine Card — rutin dışı kart numarası)
    - **T/C** (Tail/Type Code — kuyruk veya tip kodu)
    - **P/N** (Part Number — parça numarası)
    - **S/N** (Serial Number — seri numarası)
- Bu alanlar tespit edildiğinde, fotoğraf **otomatik olarak yeniden adlandırılsın**, örn: `WO-45213_NRC-0021_TC-TC-JOY_2026-08-02.jpg`
- Kullanıcı, hangi alanların adlandırmada kullanılacağını ve sıralamasını ayarlardan özelleştirebilsin

### 3. Bulanık / Karanlık Fotoğraf Tespiti

- Laplacian varyansı (kenar keskinliği) tabanlı bulanıklık tespiti
- Histogram/parlaklık ortalaması tabanlı çok karanlık fotoğraf tespiti
- Eşik değerleri kullanıcı tarafından ayarlanabilir olsun (hassasiyet kaydırıcısı)
- Tespit edilen fotoğraflar "Kalitesi Düşük" filtresinde listelensin

### 4. Benzer/Aynı Fotoğraf Gruplama

- **Perceptual hash (pHash/dHash)** ile birebir veya çok yakın kopyaların hızlı tespiti
- **Görüntü embedding modeli** (MediaPipe Image Embedder veya MobileNet tabanlı embedding çıkarımı) ile anlamsal benzerlik (aynı sahnenin farklı açıları, seri çekimler) tespiti
- Embedding vektörleri arasında kosinüs benzerliği hesaplanarak kümeleme (clustering) yapılsın
- Her grup için "en iyi" fotoğraf otomatik önerilsin (netlik, çözünürlük, yüz ifadesi vb. skoruna göre)

### 5. "Silinmesi Muhtemel Fotoğraflar" Listesi

Şu kriterlere göre otomatik oluşturulan akıllı liste:

- Bulanık/çok karanlık fotoğraflar
- Tekrar eden/neredeyse aynı fotoğraflar (en iyisi hariç)
- Çok küçük boyutlu veya bozuk ekran görüntüleri
- Kullanıcı onayı olmadan **hiçbir şey otomatik silinmesin** — sadece öneri listesi sunulsun

### 6. Akıllı Albümler

Otomatik oluşturulan, dinamik (kural tabanlı) albümler:

- **Belgeler** (OCR + belge sınıflandırması)
- **Alışveriş** (fatura + ürün fotoğrafları)
- **İş** (W/O, NRC, T/C, P/N, S/N içeren fotoğraflar)
- **Seyahat** (manzara + konum/EXIF verisi + uçak koltuğu gibi nesne tespitleri)
- Kullanıcı kendi kural tabanlı albümlerini de tanımlayabilsin (örn: "içinde 'kablo' geçen ve son 30 gün içinde çekilen fotoğraflar")

### 7. Nesne Bazlı Görsel Arama

- Kullanıcı arama çubuğuna "kahve makinesi", "uçak koltuğu", "kablo" gibi terimler yazdığında, Object Detection modelinin ürettiği etiketler üzerinden eşleşen fotoğraflar listelensin
- Arama sonuçları güven skoruna (confidence score) göre sıralansın

### 8. Kayıt Türü Sınıflandırması (Küçük Metin Sınıflandırma Modeli)

- OCR çıktısındaki metin, hafif bir on-device metin sınıflandırma modeliyle (örn: TFLite ile dönüştürülmüş küçük bir BERT-mini veya basit bir n-gram/embedding tabanlı sınıflandırıcı) "iş emri", "fatura", "kimlik/etiket", "genel belge" gibi kayıt türlerine ayrılsın

### 9. Toplu İşlemler

- Kategori bazlı toplu taşıma (albüme ekleme) ve toplu silme
- Çoklu seçim + "hepsini seç" desteği
- Silmeden önce çöp kutusuna (soft delete) taşıma, geri alma seçeneği

---

## MİMARİ VE VERİ AKIŞI

1. **Tarama servisi (WorkManager):** Yeni eklenen/değişen fotoğrafları arka planda tespit eder
2. **ML Pipeline (sırayla veya paralel):**
    - Görüntü ön işleme (resize, normalize)
    - Image Classification → genel kategori
    - Object Detection → nesne etiketleri
    - OCR (ML Kit Text Recognition) → metin blokları
    - Alan ayrıştırma (regex/kural motoru) → W/O, NRC, T/C, P/N, S/N
    - Embedding çıkarımı → benzerlik vektörü
    - Perceptual hash hesaplama
    - Bulanıklık/karanlık skoru hesaplama
3. **Sonuçların Room veritabanına yazılması** (fotoğraf ID, kategori, etiketler, OCR metni, embedding, hash, kalite skoru)
4. **UI katmanı:** Jetpack Compose ile galeri görünümü, kategori sekmeleri, arama, akıllı albümler, "silinmesi muhtemel" ekranı

---

## UI/UX GEREKSİNİMLERİ

- Ana ekran: Kategori sekmeleri (Tümü, Ekran Görüntüsü, Belge, Fatura, Yemek, Ürün, Evcil Hayvan, Manzara, İş)
- Arama çubuğu: hem metin (OCR) hem nesne bazlı arama
- "Silinmesi Muhtemel" ekranı: gruplanmış görünüm (bulanık / karanlık / tekrar eden)
- Akıllı albüm yönetim ekranı: kural oluşturma/düzenleme arayüzü
- Fotoğraf detay ekranı: tespit edilen tüm etiketler, OCR metni, ayrıştırılmış alanlar (W/O, NRC, vb.) düzenlenebilir şekilde gösterilsin
- Ayarlar: ML hassasiyet eşikleri, adlandırma şablonu, gizlilik/izin yönetimi
- Koyu tema desteği, Material 3 tasarım dili

---

## PERFORMANS VE GİZLİLİK NOTLARI

- Tüm ML çıkarımları **cihaz üzerinde** çalışmalı, ağ isteği yapılmamalı
- Büyük galerilerde (10.000+ fotoğraf) ilk tarama arka planda, düşük öncelikli WorkManager görevleriyle kademeli yapılmalı; pil/performans etkisini azaltmak için NPU/GPU delegate (LiteRT GPU delegate) kullanılmalı
- Kullanıcıya ilk kurulumda hangi verilerin sadece cihazda tutulduğu açıkça belirtilmeli

---

## TESLİM EDİLECEKLER (AI'DAN BEKLENEN ÇIKTI)

1. Proje mimarisi ve klasör yapısı önerisi
2. Kullanılacak model önerileri (hangi hazır LiteRT/ML Kit modelleri, hangi noktada custom model gerekir)
3. Room veritabanı şeması (tablolar: photos, categories, ocr_results, embeddings, tags)
4. ML pipeline'ın Kotlin implementasyonu (adım adım, coroutine tabanlı)
5. Örnek regex/kural motoru: W/O, NRC, T/C, P/N, S/N alanlarının OCR metninden ayrıştırılması
6. Jetpack Compose ile örnek ana ekran ve fotoğraf detay ekranı UI kodu
7. Perceptual hash ve embedding benzerlik hesaplama algoritmasının kod örneği
8. Gradle bağımlılık listesi (ML Kit, LiteRT, MediaPipe, Room, WorkManager, Coil)

---

## ÖNCELİK SIRASI (Aşamalı Geliştirme Önerisi)

1. **MVP:** Galeri tarama + temel kategori sınıflandırma (Image Classification) + ML Kit OCR ile ekran görüntüsü/belge ayrımı
2. **Faz 2:** Bulanık/karanlık tespiti + perceptual hash ile tam kopya gruplama
3. **Faz 3:** Object Detection ile nesne bazlı arama + akıllı albümler
4. **Faz 4:** Embedding tabanlı benzerlik kümeleme + "silinmesi muhtemel" listesi
5. **Faz 5:** W/O, NRC, T/C, P/N, S/N alan ayrıştırma + otomatik yeniden adlandırma (özel/teknik kullanım senaryosu)
6. **Faz 6:** Custom LiteRT Object Detection modeli eğitimi ve entegrasyonu (kullanıcının kendi ekipman/parça görselleriyle fine-tune)

---
⬆ [[00_Gelen_Kutusu/00_Gelen_Kutusu|Gelen Kutusu]] · 🏠 [[Vault|Ana Sayfa]]
