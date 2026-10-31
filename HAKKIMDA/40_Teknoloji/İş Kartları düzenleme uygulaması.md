# İş Kartları düzenleme uygulaması

#teknoloji

## Genel Tanım

Samsung Galaxy S23 ve sonrası modeller için, tamamen cihaz üzerinde (on-device) çalışan, internet bağlantısı gerektirmeyen bir Android galeri düzenleme uygulaması geliştir. Uygulama, kullanıcının fotoğraf galerisini yapay zeka destekli görüntü analizi ve OCR (optik karakter tanıma) kullanarak otomatik olarak kategorize etsin, tekrarlayan/bulanık/kötü fotoğrafları tespit etsin ve metin içeriğine göre akıllı isimlendirme ve arama yapabilsin.

Uygulama özellikle **teknik/endüstriyel kullanım** (bakım kayıtları, iş emirleri, parça etiketleri) ile **günlük kullanım** (ekran görüntüsü, fatura, yemek, evcil hayvan, seyahat fotoğrafları) senaryolarını aynı anda desteklemeli.

## Hedef Platform ve Teknoloji Yığını

- **Platform:** Native Android (Kotlin, Jetpack Compose ile modern UI)
- **Minimum hedef cihaz:** Samsung Galaxy S23 ve sonrası (Snapdragon 8 Gen 2 / Exynos 2200+, NPU/GPU hızlandırmalı ML çıkarımı için yeterli donanım)
- **minSdkVersion:** Android 13 (API 33) öneriliyor; gerekirse API 31'e kadar düşürülebilir
- **ML/AI çerçevesi:**
  - Google ML Kit (OCR / Text Recognition v2, on-device)
  - LiteRT (eski adıyla TensorFlow Lite) — Image Classification ve Object Detection için
  - MediaPipe — görüntü embedding / benzerlik çıkarımı ve gerekiyorsa yüz/nesne tespiti için
  - Gerekirse özel eğitilmiş `.tflite` modelleri (custom LiteRT Object Detection modeli) entegre edilecek şekilde modüler bir ML katmanı tasarla
- **Depolama:** Room (SQLite) — fotoğraf meta verisi, kategori etiketleri, OCR sonuçları, embedding vektörleri ve hash değerleri için yerel veritabanı
- **Arka plan işleme:** WorkManager — galerideki yeni/değişen fotoğrafları arka planda tarayıp analiz etmek için
- **Görüntü işleme:** `MediaStore` API üzerinden galeri erişimi + Coil/Glide ile önizleme yükleme

> Not: Uygulama tamamen offline çalışmalı; hiçbir fotoğraf veya metin veri harici bir sunucuya gönderilmemeli (gizlilik açısından kritik, özellikle iş/bakım verileri için).

## Temel Özellikler

### 1. Otomatik Kategorizasyon

Kullanıcı tarafından referans fotoğraflar galeriden seçilecek. Referans fotoğrafa göre telefonun dahili yapay zekasından faydalanılarak aynı türden fotoğraflar kategorize edilir. Kullanıcı referans fotoğrafların üzerinden alınması gereken sabit verileri seçebilecek ve bu sayede aynı formattaki fotoğrafların veri bilgileri toplanacak.

- LiteRT Image Classification modeli (MobileNetV3 veya EfficientNet-Lite tabanlı, gerekirse fine-tune edilmiş) genel sahne sınıflandırması yapsın
- LiteRT Object Detection modeli (kahve makinesi, uçak koltuğu, kablo vb. gibi spesifik nesneleri tespit etmek için) nesne bazlı etiketleme yapsın
- Ekran görüntüsü tespiti için hem meta veri (dosya adı, çözünürlük/en-boy oranı, EXIF eksikliği) hem de görsel sınıflandırma birlikte kullanılsın

### 2. ML Kit OCR Entegrasyonu (Metin Tabanlı Arama ve Etiketleme)

- ML Kit Text Recognition v2 kullanılarak fotoğraflardaki metinler blok, satır ve kelime seviyesinde çıkarılsın
- Kullanıcının tanımladığı anahtar kelimeler/desenler (regex destekli) fotoğraf metinlerinde aransın ve eşleşen fotoğraflar otomatik kategorize edilsin
- Aşağıdaki alan türleri özel olarak ayrıştırılsın (parça/iş emri takibi için): W/O (Work Order), NRC (Non-Routine Card), T/C (Tail/Type Code), P/N (Part Number), S/N (Serial Number)
- Bu alanlar tespit edildiğinde, fotoğraf otomatik olarak yeniden adlandırılsın, örn: `WO-45213_NRC-0021_TC-TC-JOY_2026-08-02.jpg`
- Kullanıcı, hangi alanların adlandırmada kullanılacağını ve sıralamasını ayarlardan özelleştirebilsin

### 3. Bulanık / Karanlık Fotoğraf Tespiti

- Laplacian varyansı (kenar keskinliği) tabanlı bulanıklık tespiti
- Histogram/parlaklık ortalaması tabanlı çok karanlık fotoğraf tespiti
- Eşik değerleri kullanıcı tarafından ayarlanabilir olsun (hassasiyet kaydırıcısı)
- Tespit edilen fotoğraflar "Kalitesi Düşük" filtresinde listelensin

### 4. Benzer/Aynı Fotoğraf Gruplama

- Perceptual hash (pHash/dHash) ile birebir veya çok yakın kopyaların hızlı tespiti
- Görüntü embedding modeli (MediaPipe Image Embedder veya MobileNet tabanlı embedding çıkarımı) ile anlamsal benzerlik (aynı sahnenin farklı açıları, seri çekimler) tespiti
- Embedding vektörleri arasında kosinüs benzerliği hesaplanarak kümeleme (clustering) yapılsın
- Her grup için "en iyi" fotoğraf otomatik önerilsin (netlik, çözünürlük, yüz ifadesi vb. skoruna göre)

### 5. "Silinmesi Muhtemel Fotoğraflar" Listesi

Şu kriterlere göre otomatik oluşturulan akıllı liste:

- Bulanık/çok karanlık fotoğraflar
- Tekrar eden/neredeyse aynı fotoğraflar (en iyisi hariç)
- Çok küçük boyutlu veya bozuk ekran görüntüleri
- Kullanıcı onayı olmadan hiçbir şey otomatik silinmesin — sadece öneri listesi sunulsun

### 6. Akıllı Albümler

Otomatik oluşturulan, dinamik (kural tabanlı) albümler: Belgeler (OCR + belge sınıflandırması), Alışveriş (fatura + ürün fotoğrafları), İş (W/O, NRC, T/C, P/N, S/N içeren fotoğraflar), Seyahat (manzara + konum/EXIF verisi + uçak koltuğu gibi nesne tespitleri).

Kullanıcı kendi kural tabanlı albümlerini de tanımlayabilsin (örn: "içinde 'kablo' geçen ve son 30 gün içinde çekilen fotoğraflar").

### 7. Nesne Bazlı Görsel Arama

Kullanıcı arama çubuğuna "kahve makinesi", "uçak koltuğu", "kablo" gibi terimler yazdığında, Object Detection modelinin ürettiği etiketler üzerinden eşleşen fotoğraflar listelensin. Arama sonuçları güven skoruna (confidence score) göre sıralansın.

### 8. Kayıt Türü Sınıflandırması

OCR çıktısındaki metin, hafif bir on-device metin sınıflandırma modeliyle (örn. TFLite ile dönüştürülmüş küçük bir BERT-mini veya basit bir n-gram/embedding tabanlı sınıflandırıcı) "iş emri", "fatura", "kimlik/etiket", "genel belge" gibi kayıt türlerine ayrılsın.

### 9. Toplu İşlemler

- Kategori bazlı toplu taşıma (albüme ekleme) ve toplu silme
- Çoklu seçim + "hepsini seç" desteği
- Silmeden önce çöp kutusuna (soft delete) taşıma, geri alma seçeneği

## Mimari ve Veri Akışı

1. **Tarama servisi (WorkManager):** Yeni eklenen/değişen fotoğrafları arka planda tespit eder
2. **ML Pipeline (sırayla veya paralel):** görüntü ön işleme (resize, normalize) → Image Classification (genel kategori) → Object Detection (nesne etiketleri) → OCR (metin blokları) → alan ayrıştırma (regex/kural motoru: W/O, NRC, T/C, P/N, S/N) → embedding çıkarımı (benzerlik vektörü) → perceptual hash hesaplama → bulanıklık/karanlık skoru hesaplama
3. **Sonuçların Room veritabanına yazılması** (fotoğraf ID, kategori, etiketler, OCR metni, embedding, hash, kalite skoru)
4. **UI katmanı:** Jetpack Compose ile galeri görünümü, kategori sekmeleri, arama, akıllı albümler, "silinmesi muhtemel" ekranı

## UI/UX Gereksinimleri

- Ana ekran: kategori sekmeleri (Tümü, Ekran Görüntüsü, Belge, Fatura, Yemek, Ürün, Evcil Hayvan, Manzara, İş)
- Arama çubuğu: hem metin (OCR) hem nesne bazlı arama
- "Silinmesi Muhtemel" ekranı: gruplanmış görünüm (bulanık / karanlık / tekrar eden)
- Akıllı albüm yönetim ekranı: kural oluşturma/düzenleme arayüzü
- Fotoğraf detay ekranı: tespit edilen tüm etiketler, OCR metni, ayrıştırılmış alanlar (W/O, NRC, vb.) düzenlenebilir şekilde gösterilsin
- Ayarlar: ML hassasiyet eşikleri, adlandırma şablonu, gizlilik/izin yönetimi
- Koyu tema desteği, Material 3 tasarım dili

## Performans ve Gizlilik Notları

- Tüm ML çıkarımları cihaz üzerinde çalışmalı, ağ isteği yapılmamalı
- Büyük galerilerde (10.000+ fotoğraf) ilk tarama arka planda, düşük öncelikli WorkManager görevleriyle kademeli yapılmalı; pil/performans etkisini azaltmak için NPU/GPU delegate (LiteRT GPU delegate) kullanılmalı
- Kullanıcıya ilk kurulumda hangi verilerin sadece cihazda tutulduğu açıkça belirtilmeli

## Teslim Edilecekler (AI'dan Beklenen Çıktı)

1. Proje mimarisi ve klasör yapısı önerisi
2. Kullanılacak model önerileri (hangi hazır LiteRT/ML Kit modelleri, hangi noktada custom model gerekir)
3. Room veritabanı şeması (tablolar: photos, categories, ocr_results, embeddings, tags)
4. ML pipeline'ın Kotlin implementasyonu (adım adım, coroutine tabanlı)
5. Örnek regex/kural motoru: W/O, NRC, T/C, P/N, S/N alanlarının OCR metninden ayrıştırılması
6. Jetpack Compose ile örnek ana ekran ve fotoğraf detay ekranı UI kodu
7. Perceptual hash ve embedding benzerlik hesaplama algoritmasının kod örneği
8. Gradle bağımlılık listesi (ML Kit, LiteRT, MediaPipe, Room, WorkManager, Coil)

## Öncelik Sırası (Aşamalı Geliştirme Önerisi)

1. **MVP:** Galeri tarama + temel kategori sınıflandırma (Image Classification) + ML Kit OCR ile ekran görüntüsü/belge ayrımı
2. **Faz 2:** Bulanık/karanlık tespiti + perceptual hash ile tam kopya gruplama
3. **Faz 3:** Object Detection ile nesne bazlı arama + akıllı albümler
4. **Faz 4:** Embedding tabanlı benzerlik kümeleme + "silinmesi muhtemel" listesi
5. **Faz 5:** W/O, NRC, T/C, P/N, S/N alan ayrıştırma + otomatik yeniden adlandırma (özel/teknik kullanım senaryosu)
6. **Faz 6:** Custom LiteRT Object Detection modeli eğitimi ve entegrasyonu (kullanıcının kendi ekipman/parça görselleriyle fine-tune)

## İskelet İçin Hazır Promptlar

- **İlk Ürün Yapısı ve Konsepti:** Şimdilik backend kurma, API bağlama, uygulamayı geliştirme; önce hedef kullanıcıyı, kullanıcı yolculuğunu, ekranları ve tasarım yönlerini çıkar.
- **Tasarım Yönü ve Görsel Dili:** Uygulama çocuksu görünmesin; premium, sade, sinematik ve kullanılabilir olsun.
- **Test ve İyileştirme Talimatı:** Yeni özellik ekleme, önce yaptığını temizle.

### Üretim

Şimdi yalnızca Faz 1'e başla. Amaç uygulamanın tamamını geliştirmek değil, sadece yüksek kaliteli, etkileşimli bir mobil prototip oluşturmak.

**Gereksinimler:** Android hissi versin, Flutter tarzı arayüz kullansın, frosted glass / cam efekti kullansın, akıcı animasyonlar olsun, alt menü navigasyonu olsun, büyük dokunma alanları olsun, tek elle rahat kullanılabilsin.

**Yalnızca şu ekranları oluştur:** 1) Açılış ekranı, 2) Onboarding, 3) Ana ekran.

Şimdi geliştirmeye devam etmeden önce Faz 1'i kalite kontrol et ve küçük düzeltmeleri yap.

**Kontrol listesi:** Uygulama mobilde web sitesi gibi değil gerçek Android app gibi hissettirmeli; tüm ekranlarda aynı tasarım sistemi korunmalı; butonların tamamı doğru ekrana yönlendirmeli; onboarding yalnızca ilk açılışta görünmeli ("Başla"/"Atla" sonrası ana ekrana geçmeli); mobil görünümde yatay taşma, küçük yazı, sıkışık buton veya hizalama problemi olmamalı.

Yeni özellik ekleme; AI, API, backend, veritabanı veya kullanıcı girişi ekleme. Sadece mevcut Faz 1 prototipini temizle, tutarlı hale getir ve test edilebilir durumda sabitle. İşlem bitince yeni bir checkpoint oluştur ve hangi düzeltmeleri yaptığını kısa maddelerle özetle.

![[Gemini_Generated_Image_a53ikca53ikca53i.png]]

## Kendi Algoritmalarım

Uygulama ilk ana sayfa açılışında otomatik olarak galeri taramasına başlıyor — bunu iptal et. Kullanıcı tarama işleminin tarih aralığını öncesinde belirlemek isteyebilir.

**Task Card sayfası bulma algoritması:** OCR mevcut sayfada şu verilerden en az 4 tanesini içeriyorsa bu sayfayı Task Card olarak işaretle ve diğer kategorilere bu sayfaların gitmesini öncelikli olarak engelle: "MSN", "TÜRK HAVA", "Work Order", "Description", "Revision No", "Task Card", "Date", "Page No", "FR.50.0209".

**NRC sayfası bulma algoritması:** OCR mevcut sayfada şu verilerden en az 4 tanesini içeriyorsa bu sayfayı NRC sayfası olarak işaretle ve diğer kategorilere bu sayfaların gitmesini öncelikli olarak engelle: "AIRCRAFT REGISTRATION", "MAINTENANCE CHECK NO", "WORK ORDER NO", "ESTIMATED", "CUSTOMER", "ACCEPTANCE", "ACCOUNT CODE", "MATERIAL DESCRIPTION", "ACTION TO BE TAKEN", "NON-ROUTINE WORK ITEM".

**Defter sayfası bulma algoritması:** OCR mevcut sayfada şu verilerden en az 5 tanesini içeriyorsa bu sayfayı Defter sayfası olarak işaretle ve diğer kategorilere bu sayfaların gitmesini öncelikli olarak engelle: "ADDRESS: TURKISH AIRLINES ING. HEAD OFFICE, YESILKÖY MAHALLESI", "TOTAL BLOCK TIME", "BLOCK TIME (UTC)", "APU IN-FLIGHT START PROGRAM", "AIRCRAFT MAINTENANCE LOG", "FR.50.0025", "QUANTITY FILLED OR DRAINED", "MAX ENG OIL CONSUMPTION", "COMMANDER", "THIS LOG PAGE IS APPROVED BY TURKISH".

### Faz 2

Ara sekmesine filtre eklensin: Bugün, Son 3 gün, Son 1 hafta, Son 1 ay.

### Faz 3

**Rol ve Görev:** Sen uzman bir Flutter ve Android (Kotlin) geliştiricisisin. Çevrimdışı çalışan, cihaz içi makine öğrenimi (ML Kit, MediaPipe, LiteRT) kullanan ve büyük galerileri işleyen yüksek performanslı bir havacılık teknik belge tarama ve organizasyon uygulaması geliştiriyoruz.

**Mimari ve Teknoloji Yığını:**

- UI ve Yönlendirme: Flutter (sekmesiz, tekil ana ekran mimarisi)
- Arka Plan İşleri: Android WorkManager (kalıcı) ve Dart Isolates (geçici)
- ML ve Ağır İşlemler: ML Kit (OCR), MediaPipe (sınıflandırma), MediaStore API — bu katmanlar Android/Kotlin tarafında yazılacak ve Flutter ile MethodChannel/Plugin üzerinden haberleşecek
- Veri Tabanı: SQLite (FTS5 destekli)

**Temel Geliştirme Kuralları (Kesinlikle Uyulacak):**

1. Gereksiz işlem yapma: galerideki fotoğraflar her açılışta baştan taranmayacak. MediaStore ID, dateModified, boyut ve içerik hash'i saklanarak sadece yeni/değişen dosyalar işlenecek.
2. Kademeli ML hattı: her fotoğrafa doğrudan tam OCR yapılmayacak. Sıra: ucuz ön kontrol → düşük çözünürlüklü belge sınıflandırması (Compass, NRC, Task Card vb.) → bölgesel OCR → gerekirse tam OCR.
3. Akıllı ayrıştırma: veri çıkarımı sadece regex ile yapılmayacak. Regex biçimi + anahtar kelimeye yakınlık + dikey konum + şablon bölgesi kombinasyonu ile ortak bir "güven puanı" hesaplanacak.
4. Platform ayrımı: Flutter sadece UI, navigasyon ve veri sunumundan sorumlu olacak. MediaStore, WorkManager ve ML işlemleri Kotlin tarafında kalacak.
5. Geri alınabilirlik: dosya yeniden adlandırma işlemleri doğrudan yapılmayacak, çakışma kontrolü yapılacak ve eski ad saklanarak "Geri Al (Rollback)" mekanizması kurulacak.
6. Performans: UI thread'i asla bloklanmayacak. İşlemler Isolate'lerde veya native asenkron kuyruklarda yapılacak.

Projeyi temiz bir şekilde başlatmak için `.dart_tool/`, `build/`, `android/.gradle/`, `windows/` (kullanılmayacaksa) klasörlerini yoksayacak kusursuz bir `.gitignore` dosyası oluştur ve proje yapısını temizle.

Bu bağlam anlaşıldıysa "BAĞLAM ONAYLANDI" yaz. Ardından ilk aşama görevleri verilecek.

**Aşama 1: Temel Altyapı ve Veri Tabanı**

Uygulamanın temel veri tabanı mimarisini ve tarama durumu mekanizmasını oluştur.

1. SQLite (sqflite veya drift kullanarak) veri tabanını kur.
2. Tam metin araması (FTS5) destekleyen bir yapı oluştur. A/C, W/O, NRC, P/N, S/N, Task Card için normal indeks, tam OCR metni için FTS kullan. FTS aramalarında tam eşleşmelerin, kısmi eşleşmelerden daha yüksek puan almasını sağla.
3. Tarama geçmişi için tablo: mediaStoreId, dateModified, fileSize, width, height, fastContentHash, ocrModelVersion.
4. OCR ve teknik alan sonuçlarını saklamak için tablo: rawValue, normalizedValue, confirmedValue, boundingBox, confidenceScore, sourceMethod.
5. Dosya yeniden adlandırma geçmişi için tablo: originalDisplayName, currentDisplayName, renameTemplate, renamedAt, renameStatus, rollbackAvailable (boolean).

Sadece DB mimarisini ve ilgili Dart modellerini yaz.

**Aşama 2: Kademeli ML Pipeline ve Native Köprü**

Android (Kotlin) ile Flutter arasındaki MethodChannel köprüsünü ve kademeli analiz hattını kur.

1. Android tarafında Kotlin ile MediaStore'dan görselleri okuyan, Flutter'dan gelen ID listesini kontrol ederek sadece değişen/yeni dosyaları seçen sorguyu yaz.
2. Kotlin tarafında şu adımları izleyen bir ML hattı kur: boyut/hash hesabı → MediaPipe düşük çözünürlük sınıflandırması → bölgesel veya tam OCR.
3. Havacılık karakter hataları için Kotlin tarafında normalizasyon fonksiyonu yaz: (O→0, I→1, S→5, B→8).
4. Çıkan sonuçları Flutter'a döndürecek MethodChannel yapısını kur. WorkManager arayüzlerini hazırla.

**Aşama 3: Geometri Destekli Ayrıştırma**

OCR'dan dönen metinleri ve bounding box koordinatlarını analiz edecek akıllı bir Dart sınıfı yaz.

1. Dört bileşenli bir puanlama sistemi oluştur: regex eşleşme puanı + anahtar kelimeye koordinat yakınlığı + sayfadaki dikey konum + şablon bölgesi.
2. Aynı şablonda kullanıcının yaptığı düzeltmeleri (örn. "TC-JN8" → "TC-JNB") kaydedecek ve sonraki OCR aday puanlarını güncelleyecek yerel bir kural/öğrenme mekanizması yaz.

**Aşama 4: UI/UX, Birleştirilmiş Ana Ekran ve İş Kuyruğu**

Uygulamanın sekmesiz (no bottom nav) ön yüzünü, birleştirilmiş arama yapısını ve işlem durumu ekranlarını geliştir.

1. Tekil ana ekran: alt sekme (BottomNav) yapısını kaldır. Uygulama tek bir ana ekrana sahip olacak. Ekranın sağ üst köşesine (AppBar) "Ayarlar" butonunu yerleştir. Ayarlar sayfasında "Galeriyi yeniden tara" butonu olmayacak (bu fonksiyon ana ekranda halledilecek).
2. Birleştirilmiş İş Kartları görünümü: eski "İş Kartları" ve "Bul & İncele" özelliklerini bu ana ekranda birleştir. Liste, "İş Paketi" klasörleri şeklinde gruplanmış olacak (aynı A/C ve W/O değerine sahip fotoğraflar tek klasörde). AppBar'ın altına arama kutucuğunu ve filtreleme butonunu yerleştir.
3. Detay sayfası yönlendirmesi: bir belgeye/fotoğrafa tıklandığında resim doğrudan tam ekran açılmayacak; bunun yerine "Kayıt Detay" ekranı açılacak. Detay ekranında aynı W/O ve A/C'ye ait diğer belgeler/kayıtlar da listelenecek.
4. Tam ekran ve paylaşım: "Kayıt Detay" ekranındaki resmin üzerine tıklandığında resim tam ekran açılacak; bu görünüme bir "Paylaş" butonu ekle.
5. İş kuyruğu göstergesi: arka plan işlemlerini (bekliyor, OCR yapılıyor vb.) gösteren modern bir UI yap.
6. Routing işlemlerini GoRouter veya standart Navigator 2.0 ile kur, böylece ana ekrandan detay sayfasına geçiş pürüzsüz olsun.

**Aşama 5: Çoklu Yeniden Adlandırma (MediaStore) ve Dışa Aktarma**

Toplu/tekil dosya yeniden adlandırma ve raporlama/export mekanizmalarını yaz.

1. Toplu MediaStore yeniden adlandırma: ana ekrandaki klasör/liste görünümlerinde "Çoklu Seçim" modunu aktifleştir. Kullanıcı birden fazla kayıt seçip bu dosyaları toplu şekilde MediaStore üzerinden yeniden adlandırabilsin.
2. Tekil ve manuel adlandırma: yeniden adlandırma özelliği "Kayıt Detay" sayfasında da opsiyonel olarak bulunsun. Kullanıcı sistemin önerdiği yeni ismi kabul edebilsin veya manuel olarak düzenleyebilsin.
3. Güvenlik ve geri alma: Android 10+ Scoped Storage izinlerini sağla. Eski isimleri veri tabanında tutarak "Geri Al" (Rollback) opsiyonu sun. Aynı isimde dosya varsa çakışma kontrolü yap.
4. Offline export: seçilen belgeleri PDF Özet (resim + OCR), CSV teknik alan listesi ve ZIP olarak dışa aktaran modülü yaz.

## İlgili Bağlantılar

- [[40_Teknoloji|Teknoloji]]
- [[40_Teknoloji inkflow|inkflow — PDF OCR Süre Tahmin Modülü]]
- [[Kod Derleme ve Yayınlama Komutları]]
- [[Locpic]]
