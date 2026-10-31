---
notion-bases: true
schema:
- id: type
  name: Type
  type: select
  visible: true
  width: 140
  options:
  - value: Kişi
  - value: rutin
  - value: yer
    color: '#d4f1c0'
  - value: kod
    color: '#fde8c8'
  - value: hafıza
    color: '#ffd6d6'
  - value: iş referansı
    color: '#d6f0f0'
  - value: teknik bilgi
    color: '#f0d6f0'
- id: etiket
  name: Etiket
  type: multiselect
  visible: true
  width: 140
  options:
  - value: '#Akraba'
  - value: '#Anne_Tarafi'
  - value: iga
  - value: Servis
- id: Ev lokasyon
  name: Ev lokasyon
  type: url
  visible: true
  width: 200
- id: plaka
  name: Plaka
  type: text
  visible: true
  width: 200
- id: kapak
  name: Kapak
  type: image
  visible: true
  width: 150
- id: campo_1785607206518
  name: New field
  type: select
  visible: true
  width: 150
  options:
  - value: 💧Çeşme, su alma yerleri
    color: '#e2d9f3'
views:
- id: default
  type: table
  filters: []
  sorts: []
  hiddenColumns: []
  columnWidths: {}
  pinnedColumnId: null
  rowHeight: compact
  columnOrder:
  - campo_1785607206518
  - plaka
  - type
  - etiket
  - Ev lokasyon
  - kapak
- id: e5605e77-7cde-4cfb-9924-99fbd5d91e1c
  type: gallery
  filters: []
  sorts: []
  hiddenColumns: []
  columnWidths: {}
  pinnedColumnId: null
  name: Gallery
  includeSubfolders: true
  galleryCoverField: kapak
üst-sayfa: '[[90_Arşiv/90_Arşiv|Arşiv]]'
ana-sayfa: '[[Vault|Ana Sayfa]]'
---

> [!tip] Notion Bases
> This file is a database. Open it to see the table view.

<!-- ATOMIK-RELATIONS:START -->
> [!abstract] Bağlantılar
> [[90_Arşiv/90_Arşiv|Arşiv]] · [[Vault|Ana Sayfa]]
<!-- ATOMIK-RELATIONS:END -->
