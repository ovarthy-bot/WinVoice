# Evdeki fiziksel varlıkların yaşam döngüsü yönetimi

#teknoloji #flutter

![[ChatGPT Image 19 Ağu 2026 14_56_07.png]]

Flutter ile Android öncelikli, daha sonra iOS desteğine uygun olacak şekilde premium bir **Ev Cihazı Bakım, Garanti ve Servis Takip Uygulaması** geliştir.

Uygulamanın temel amacı, evde bulunan bakım gerektiren cihazların satın alma, garanti, servis, bakım ve bakım geçmişi bilgilerinin tek yerde tutulmasıdır.

Bu uygulama basit bir QR takip uygulaması değildir. QR kod yalnızca cihazın detay sayfasına hızlı erişim sağlayan yardımcı bir yöntemdir.

Ana veri modeli şu mantıkla kurulmalıdır: **Ev → Cihaz → Bakım Kalemleri → Bakım Kayıtları / Geçmiş**

Bir cihazın birden fazla bakım gerektiren parçası veya işlemi olabileceğini sistemin temelinde kabul et. Örneğin bir kahve makinesi:

- Demleme ünitesini yıkama
- Kahve yağı temizleme tableti kullanma
- Kireç temizliği
- Su filtresi değiştirme

gibi birbirinden bağımsız bakım kalemlerine sahip olabilir. Her bakım kaleminin kendi bakım adı, açıklaması, bakım türü, bakım periyodu, son bakım tarihi, sonraki bakım tarihi ve geçmiş bakım kayıtları olmalıdır.

## Teknoloji

Uygulamayı Flutter ve Dart kullanarak geliştir. Kod modüler, okunabilir, sürdürülebilir, null-safety uyumlu, reusable widget yapısına sahip, feature-based veya clean architecture yaklaşımına yakın olmalıdır.

State management için aşırı karmaşık olmayan modern bir yöntem kullan. Tercihen Riverpod.

İlk sürümde backend kurma, REST API oluşturma, Firebase bağlama, kullanıcı hesabı oluşturma, cloud sync yapma **YAPMA**. Uygulama önce tamamen yerel çalışmalıdır.

Verileri cihaz üzerinde kalıcı saklamak için uygun bir local database kullan. Tercihen Isar veya Drift. SharedPreferences yalnızca küçük uygulama ayarları için kullanılabilir.

## Tasarım Felsefesi

Uygulama çocuksu görünmemeli, jenerik Flutter demo uygulaması gibi görünmemeli, gereksiz renk kullanmamalı, fazla ikon kullanmamalı, aşırı kart kullanımından kaçınmalı.

Tasarım dili: **premium + sade + sinematik + fonksiyonel**.

Apple Home, premium otomobil uygulamaları ve modern fintech uygulamalarından esinlenebilirsin ancak hiçbirini birebir kopyalama. Ana tema olarak koyu tema kullan.

**Renk yaklaşımı:**

- Ana arka plan: koyu grafit / siyaha yakın
- Yüzeyler: çok koyu gri
- Ana metin: kırık beyaz
- İkincil metin: gri
- Yeşil: normal durum
- Amber/turuncu: yaklaşan bakım
- Kırmızı: gecikmiş bakım
- Mavi/cyan: bilgi veya garanti

Durum renklerini yalnızca gerekli olduğunda kullan. Gradient, glow ve blur efektlerini abartma. Animasyonlar kısa, doğal ve premium hissettirmeli.

## Ana Navigasyon

Alt navigation bar kullan. Ana sekmeler:

1. Ana Sayfa
2. Cihazlar
3. Geçmiş
4. Ayarlar

QR tarama daha sonra hızlı aksiyon olarak erişilebilir ancak ana sekme olmak zorunda değildir.

## Ana Sayfa

Ana ekranın temel sorusu şu olmalıdır: **"Bugün ilgilenmem gereken bir şey var mı?"**

Ekranın üst kısmında **Ev Sağlığı** başlığı kullan. Altında özet bilgi: geciken bakım sayısı, yaklaşan bakım sayısı, yakında bitecek garanti sayısı. Ancak ana ekranı istatistik dashboard'una dönüştürme; kullanıcıya aksiyon gerektiren öğeleri öne çıkar.

Örnek — **Dikkat Edilmesi Gerekenler:**

- Daikin Klima — Bakım 18 gün gecikti
- Roborock Q8 — Ana fırça bakımı 12 gün sonra
- Samsung TV — Garanti 43 gün sonra bitiyor

Ardından **Cihazlarım** listesi göster. Her cihaz satırında cihaz adı, kategori veya oda, genel durum, varsa en kritik bakım durumu yer alsın.

Örnek: **Philips Kahve Makinesi** — Mutfak — 1 bakım gecikmiş · 2 yaklaşan

Ana ekranda aynı cihazın bütün bakım kalemlerini ayrı ayrı gösterme.

## Cihazlar Ekranı

Tüm cihazları göster. Üstte arama alanı olsun.

**Filtre seçenekleri:** Tümü, Bakım Gerekiyor, Yaklaşan, Garanti, Sorunsuz.

Cihaz kartı veya satırı: cihaz görseli, cihaz adı, kategori, oda, bakım durumu, garanti durumu bilgilerini sade şekilde göster. Liste ve kart yapısını aşırı yoğunlaştırma.

## Uygulamaya Varsayılan Olarak Eklenecek Eşyalar

- Yazıcı — düzgün basmama
- Kahve makinesi — temizlikler
- Robot süpürge — ana fırça temizliği
- Klima — filtre temizliği
- Diş fırçası başlığı — değişim

## Yeni Cihaz Ekleme

İlk cihaz oluşturma akışı kısa olmalıdır.

**Zorunlu alanlar:** cihaz adı, kategori.

**Opsiyonel alanlar:** marka, model, seri numarası, oda/konum, cihaz fotoğrafı, satın alma tarihi, satın alma fiyatı, garanti bitiş tarihi, opsiyonel son kullanma tarihi, servis adı, servis telefon numarası, servis e-posta, servis web sitesi, notlar.

Kullanıcıyı ilk aşamada bütün alanları doldurmaya zorlama. Cihaz oluşturulduktan sonra bilgiler sonradan düzenlenebilsin.

## Cihaz Detay Ekranı

Bu ekran uygulamanın en önemli ekranlarından biri olmalıdır.

**Üst bölüm:** cihaz görseli, cihaz adı, marka/model, oda/konum, genel durum.

Örnek: **Philips LatteGo 5400** — Mutfak — `1 bakım yaklaşıyor`

**Bilgi bölümü:**

- Satın Alma: 12 Haziran 2024
- Garanti: 12 Haziran 2027 — 10 ay kaldı
- Servis: Yetkili servis bilgileri

### Bakım Planı

Cihazın tüm bakım kalemleri burada gösterilsin.

Örnek:

- **Demleme Ünitesi** — Yıkama — Son bakım: 16 Ağustos, Sonraki: 23 Ağustos, `4 gün kaldı`
- **Kahve Yağı Temizliği** — Temizleme tableti — Son bakım: 2 Ağustos, Sonraki: 1 Eylül, `13 gün kaldı`
- **Kireç Temizliği** — Son bakım: 20 Temmuz, Sonraki: 18 Ekim

Her bakım satırına dokunulduğunda bakım detay ekranı açılsın.

Cihaz detay ekranının altında hızlı işlemler: Bakım Ekle, Servis, Belgeler, Geçmiş, QR Etiketi.

## Bakım Kalemi Sistemi

Her cihazın birden fazla bakım kalemi olabilir. Bakım kalemi oluştururken: bakım adı, kısa açıklama, bakım türü, bakım periyodu, son bakım tarihi, sonraki bakım tarihi, opsiyonel talimat, opsiyonel kullanılan ürün, opsiyonel not alanları bulunmalıdır.

İlk versiyonda bakım türlerini sadece iki kategoriyle sınırla:

### Periyodik Bakım

Belirli gün veya ay aralığıyla tekrar eder. Örneğin her 7 gün, her 30 gün, her 3 ay, her 6 ay, her 12 ay.

### Manuel Bakım

Sistem otomatik tarih hesaplamaz; kullanıcı gerektiğinde tamamlandı olarak işaretler.

Şimdilik kullanım sayısına göre bakım, sensör bağlantısı, cihaz API'si, IoT entegrasyonu ekleme.

## "Bakım Yapıldı" Akışı

Bakım detay ekranında büyük ama sade bir **Bakım Yapıldı** butonu olsun. Tıklanınca bottom sheet veya minimal dialog aç.

Varsayılan: **Tarih: Bugün**

Opsiyonel alanlar: not, servis, maliyet. Kaydet butonu: **Bakımı Kaydet**

Bakım kaydedildikten sonra: son bakım tarihi güncellensin, bakım kaydı geçmişe eklensin, periyodik bakım ise sonraki bakım tarihi otomatik hesaplansın.

Örnek: Son bakım 19 Ağustos 2026, bakım periyodu 30 gün → sonraki bakım 18 Eylül 2026.

## Bakım Geçmişi

Her cihazın ayrı bakım geçmişi olmalıdır. Timeline görünümü kullan.

Örnek:

- 19 Ağustos 2026 — Demleme ünitesi yıkandı
- 2 Ağustos 2026 — Kahve yağı temizleme tableti kullanıldı
- 20 Temmuz 2026 — Kireç temizliği yapıldı
- 12 Haziran 2024 — Cihaz satın alındı

Her bakım kaydında tarih, bakım kalemi, açıklama, varsa servis, varsa maliyet, not gösterilebilir.

## Genel Geçmiş Ekranı

Ana navigasyondaki Geçmiş ekranında tüm cihazların olaylarını kronolojik sırada göster.

Örnek: Bugün — Philips Kahve Makinesi, demleme ünitesi temizlendi; 17 Ağustos — Daikin Klima, periyodik bakım yapıldı; 12 Ağustos — Roborock Q8, ana fırça değiştirildi.

Filtre: Tümü, Bakım, Servis, Satın Alma.

## Garanti Takibi

Her cihaz için satın alma tarihi ve garanti bitiş tarihi tut. Garanti bitişine kalan zamanı hesapla.

Örnek: **Garanti** — 43 gün kaldı.

Yaklaşan garanti bitişlerini ana ekranda göster. Durum sınıfları: normal, yaklaşıyor, bitmiş.

İlk sürümde garanti firması API'si veya otomatik garanti sorgulama yapma.

## Opsiyonel Son Kullanma Tarihi

Bazı cihaz, parça veya sarf öğelerinde opsiyonel son kullanma tarihi alanı bulunabilir. Alan zorunlu değildir; kullanıcı isterse ekler. Ana cihaz detayında yalnızca girilmişse göster.

## Servis Bilgileri

Her cihaz için servis bilgileri tutulabilsin: servis adı, telefon, e-posta, web sitesi, adres, not. Telefon numarası tıklanabilir olsun. Uygun olduğunda Ara / Web Sitesini Aç aksiyonları ver.

## Belgeler

Cihaz detayında Belgeler alanı bulunmalıdır. İlk versiyonda yerel dosya seçimi kullan.

**Belge türleri:** fatura, garanti belgesi, kullanım kılavuzu, servis belgesi, diğer.

Her belge: belge adı, belge türü, eklenme tarihi ile tutulabilir. Dosyalar yerel olarak saklanmalıdır. Backend kullanma.

## Cihaz Fotoğrafı

Cihaza galeriden fotoğraf seçme veya kamera ile çekme özelliği ekle. Fotoğraf cihaz listesinde küçük thumbnail olarak kullanılabilir. Fotoğraf yoksa sade kategori placeholder'ı göster. Çocuksu veya renkli illüstrasyon kullanma.

## QR Etiketi

Her cihaz için benzersiz bir ID üret. Örneğin `DEVICE-00001`.

QR kod bu ID veya uygulama deep-link bilgisine karşılık gelsin. QR cihazın bilgilerini doğrudan içinde taşımamalıdır; amacı sadece ilgili cihaz sayfasını açmaktır. Örneğin `homecare://device/DEVICE-00001`.

Cihaz detayında **QR Etiketi** seçeneği olsun. QR ekranda görüntülenebilsin, kaydedilebilsin, paylaşılabilsin. Kamera ile okutulduğunda ilgili cihaz detay ekranı açılsın. QR sistemini uygulamanın ana özelliği gibi sunma.

## Durum Motoru

Her cihaz için genel durum hesapla. Öncelik: 1) Geciken bakım, 2) Yaklaşan bakım, 3) Yaklaşan garanti, 4) Normal.

Örneğin bir kahve makinesinde 1 bakım gecikmiş, 2 bakım yaklaşmış, 1 bakım normal ise cihaz durumu: **1 bakım gecikmiş · 2 yaklaşan** olmalıdır.

## Tarih Hesaplama

Periyodik bakım tarihlerini güvenilir şekilde hesapla. Periyot gün, hafta, ay, yıl birimlerini desteklesin.

Örnek: Periyot 3 ay, son bakım 20 Temmuz 2026 → sonraki bakım 20 Ekim 2026.

Ay hesabında sadece sabit 30 günlük yaklaşım kullanma; gerçek calendar month hesabı kullan.

## Ana Sayfa Öncelik Sistemi

Ana ekrandaki öğeleri şu sırayla göster: 1) Gecikmiş bakım, 2) Bugün yapılması gereken bakım, 3) Yaklaşan bakım, 4) Yaklaşan garanti.

Kullanıcıya gereksiz bütün cihazları alarm şeklinde gösterme; sadece aksiyon gerektiren öğeleri öne çıkar.

## Arama

Cihazlarda arama yapılabilsin. Aranabilir alanlar: cihaz adı, marka, model, kategori, oda. Arama gerçek zamanlı çalışsın.

## Kategoriler

Başlangıç kategorileri: Klima, Kahve Makinesi, Robot Süpürge, Televizyon, Beyaz Eşya, Küçük Ev Aleti, Su Arıtma, Kombi, Bilgisayar, Diğer.

Kategori mimarisini büyütme; kullanıcı gerektiğinde "Diğer" kullanabilsin.

## Odalar / Konum

Basit konum sistemi: Salon, Mutfak, Yatak Odası, Çalışma Odası, Balkon, Banyo, Diğer. Alan opsiyonel olsun.

## Bildirimler

Local notification kullan. Backend veya push notification kullanma.

Bildirimler bakım yaklaşırken, bakım günü geldiğinde, bakım geciktiğinde, garanti bitişi yaklaşırken oluşturulabilsin. Kullanıcı Ayarlar ekranından bildirimleri açıp kapatabilsin.

Varsayılan hatırlatma: Bakım 7 gün önce, Garanti 30 gün önce.

Bildirim sistemini aşırı karmaşık hale getirme.

## Ayarlar

Ayarlar ekranında yalnızca gerçekten gerekli seçenekler olsun: Tema, Bakım bildirimleri, Garanti bildirimleri, Varsayılan bakım hatırlatma süresi, Veri dışa aktarma, Uygulama hakkında.

Şimdilik kullanıcı hesabı veya profil ekranı oluşturma.

## Empty State Tasarımları

Boş ekranları düzgün tasarla. Örneğin cihaz yoksa: **Henüz cihaz eklemediniz** — "Bakım ve garanti tarihlerini takip etmek için ilk cihazınızı ekleyin." — `Cihaz Ekle`

Büyük renkli illüstrasyon kullanma.

## İlk Açılış

Uzun onboarding oluşturma. Tek ekran yeterli: **"Evindeki cihazları unutma."** — "Bakım, garanti ve servis geçmişini tek yerde takip et." — `İlk Cihazımı Ekle` (isterse `Örnekle Keşfet` seçeneği olabilir).

## Örnek Demo Verileri

Development aşamasında arayüzü test etmek için demo veriler oluştur:

- **Daikin Klima** — Salon — Satın alma: 12 Haziran 2024, Bakım: 6 ayda bir, Durum: 18 gün gecikmiş
- **Philips Kahve Makinesi** — Mutfak — Demleme ünitesi yıkama: 7 gün, Kahve yağı temizliği: 30 gün, Kireç temizliği: 90 gün, Su filtresi: Manuel
- **Roborock Q8** — Salon — Ana fırça: 90 gün, Filtre: 60 gün, Yan fırça: 90 gün
- **Samsung TV** — Salon — Garanti: 43 gün sonra bitiyor

## UI Detayları

Material 3 kullan ancak varsayılan Material görünümünü olduğu gibi bırakma; custom theme oluştur.

Köşe radius orta seviyede olsun. Dev yuvarlak kartlardan kaçın. Spacing sistematik olsun: 4 / 8 / 12 / 16 / 24 / 32 gibi. Typography hierarchy güçlü olsun. Önemli tarihler ve kalan süreler daha belirgin gösterilsin (örn. **18 gün** gecikmiş).

## Animasyonlar

Animasyonları minimal tut.

**Kullanılabilir:** fade, subtle slide, shared element benzeri geçişler, button feedback, list insertion animation.

**Kullanılmamalı:** aşırı bounce, confetti, oyun hissi veren animasyonlar.

## Kullanıcı Deneyimi İlkeleri

Her ana işlem mümkün olduğunca az dokunuş gerektirsin. Özellikle **Bakım yapıldı** işlemi 5–10 saniyede tamamlanabilmelidir. Kullanıcı hiçbir kritik işlemde gereksiz form doldurmak zorunda kalmamalıdır. Opsiyonel alanları collapsed veya secondary bölümlerde göster.

## Veri Modeli

**Device:** id, name, category, brand, model, serialNumber, room, imagePath, purchaseDate, purchasePrice, warrantyEndDate, expirationDate, notes, createdAt, updatedAt

**MaintenanceItem:** id, deviceId, title, description, type, intervalValue, intervalUnit, lastMaintenanceDate, nextMaintenanceDate, instructions, productUsed, isActive, createdAt, updatedAt

**MaintenanceRecord:** id, deviceId, maintenanceItemId, date, notes, serviceName, cost, createdAt

**ServiceInfo:** id, deviceId, companyName, phone, email, website, address, notes

**DeviceDocument:** id, deviceId, title, type, filePath, createdAt

## Mimari

Kod klasör yapısını temiz tut. Örneğin:

```
lib/
  core/ (theme, routing, utils, widgets)
  features/ (dashboard, devices, maintenance, history, qr, settings)
  data/ (models, repositories, local)
```

Aşırı soyutlama yapma; ilk sürüm için gereksiz interface/repository katmanları oluşturma. Ancak ileride backend eklenebilecek şekilde local data access katmanını UI'dan ayır.

## Kod Kalitesi

Duplicate code oluşturma, dev widget build metodları kullanma, widgetları mantıklı şekilde böl, magic number kullanımını azalt, Türkçe UI metinlerini merkezi bir yapıdan yönet, date formatter helper oluştur, bakım durum hesaplamasını tek bir service/helper içerisinde tut, UI içinde business logic yazma.

## Responsive Tasarım

Ana hedef telefon ekranıdır. Galaxy S24 Ultra gibi büyük Android telefonlarda düzgün görünmelidir. Aynı zamanda daha küçük Android ekranlarında taşma olmamalıdır. Tablet desteğini tamamen optimize etmek zorunda değilsin ancak layout bozulmamalıdır.

## Performans

Liste ekranlarında gereksiz rebuild oluşturma. Resimleri optimize et. Local database işlemlerini UI thread'i gereksiz yere bloklamayacak şekilde yönet.

## Hata Durumları

Ele alınması gereken durumlar: yanlış tarih, satın alma tarihinden önce garanti bitişi, sıfır veya negatif bakım periyodu, silinmiş cihaz görseli, bulunamayan belge, bulunamayan QR cihaz ID'si, bozuk local database kaydı.

Kullanıcıya teknik exception mesajı gösterme.

## Silme İşlemleri

Cihaz silinirken confirmation göster: **Bu cihaz silinsin mi?** Cihazla birlikte bakım kalemleri, bakım geçmişi, belgeler, servis bilgilerinin de silineceği açıkça belirtilsin.

## Düzenleme

Cihaz düzenlenebilsin, bakım kalemleri düzenlenebilsin, bakım kaydı gerektiğinde düzenlenebilsin, bakım kalemi devre dışı bırakılabilsin. Bakım kalemini hemen kalıcı olarak silmek yerine "pasif" hale getirme seçeneği bulunabilir.

## İlk Sürümde Eklenmeyecekler

Kullanıcı hesabı, cloud sync, Firebase, sosyal özellik, aile üyeleri, çoklu ev, AI asistan, OCR, otomatik fatura okuma, barkod veri tabanı, servis pazaryeri, reklam, abonelik, enerji tüketimi, Home Assistant, IoT, cihaz API entegrasyonu, otomatik cihaz tanıma, kullanım sayacı sensörleri, karmaşık analitik, gamification.

Bu özelliklerin hiçbiri ilk ürünü tamamlamadan eklenmemelidir.

## Geliştirme Prensibi

Çok önemli: **Yeni özellik eklemeden önce mevcut özelliği temizle ve iyileştir.**

Her geliştirme döngüsünde sıra: 1) Mevcut ekranı çalışır hale getir, 2) UX problemlerini kontrol et, 3) Gereksiz öğeleri kaldır, 4) Görsel hiyerarşiyi düzelt, 5) Kod tekrarlarını temizle, 6) Edge case'leri düzelt, 7) Ancak bunlardan sonra sonraki özelliğe geç.

Yeni özellik eklemek, mevcut kusurları gizlemek için kullanılmamalıdır.

## Geliştirme Sırası

**Faz 1:** Theme, Navigation, Demo data, Ana Sayfa, Cihaz listesi, Cihaz detay ekranı — görsel olarak temizle.

**Faz 2:** Cihaz ekleme, Cihaz düzenleme, Local database — test et ve temizle.

**Faz 3:** Bir cihazda birden fazla bakım kalemi, Bakım oluşturma, Bakım düzenleme, Bakım yapıldı işlemi, Sonraki bakım hesaplama — test et ve temizle.

**Faz 4:** Bakım geçmişi, Genel geçmiş ekranı, Garanti durumu — test et ve temizle.

**Faz 5:** Servis bilgileri, Belgeler, Cihaz fotoğrafı — test et ve temizle.

**Faz 6:** QR üretme, QR okutma, Device deep-link — test et ve temizle.

**Faz 7:** Local notifications, Ayarlar, Empty states, hata durumları, final polish.

## Her Faz Sonunda

Her faz tamamlandığında yeni özelliğe otomatik geçme. Önce UI tutarlılığı, spacing, typography, button hierarchy, scroll davranışı, navigation, back button, form validation, dark theme, performans, responsive tasarım kontrolü yap. Sorun varsa temizle.

## Son Ürün Hissi

Uygulama açıldığında kullanıcı "Bu bir bakım kayıt tablosu" hissi almamalıdır. Şu hissi vermelidir: **"Evimdeki cihazların teknik durumunu tek bakışta görebiliyorum."**

Ana ürün değer önerisi: **Cihazı kaydet → bakım durumunu gör → işlemi tamamla → geçmişini unutma.**

Bütün tasarım ve geliştirme kararlarını bu temel akışı hızlandıracak şekilde ver.

## İlk Çalıştırmada Beklenen Sonuç

İlk tamamlanmış prototipte kullanıcı şunları yapabilmelidir: cihaz eklemek, cihaz bilgilerini düzenlemek, bir cihaza birden fazla bakım kalemi eklemek, her bakım kalemine ayrı periyot vermek, son bakım tarihini görmek, sonraki bakım tarihini otomatik hesaplatmak, bakımı tamamlandı olarak işaretlemek, bakım geçmişini görmek, garanti tarihini takip etmek, opsiyonel son kullanma tarihini tutmak, servis iletişim bilgilerini saklamak, belge eklemek, cihaz fotoğrafı eklemek, cihaz için QR üretmek, QR ile cihazı açmak, yaklaşan/geciken bakımları ana ekranda görmek, local bildirim almak, tüm verileri internet olmadan kullanmak.

Bu kapsam tamamlanmadan yeni özellik önermeye veya geliştirmeye başlama.

## İlgili Bağlantılar

- [[40_Teknoloji|Teknoloji]]
- [[Sıfırdan mobil uygulama üretim taslağı]]
- [[40_Teknoloji inkflow|inkflow — PDF OCR Süre Tahmin Modülü]]
- [[Locpic]]
