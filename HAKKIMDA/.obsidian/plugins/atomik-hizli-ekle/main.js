const {
  Plugin,
  Modal,
  SuggestModal,
  Setting,
  Notice,
  normalizePath,
} = require("obsidian");

const VAULT_HOME = "[[Vault|Ana Sayfa]]";

const TARGETS = {
  inbox: {
    folder: "00_Gelen_Kutusu",
    parentPath: "00_Gelen_Kutusu/00_Gelen_Kutusu.md",
    parentLink: "[[00_Gelen_Kutusu/00_Gelen_Kutusu|Gelen Kutusu]]",
    parentLabel: "Gelen Kutusu",
  },
  people: {
    folder: "10_Kişiler",
    parentPath: "10_Kişiler/10_Kişiler.md",
    parentLink: "[[10_Kişiler/10_Kişiler|Kişiler]]",
    parentLabel: "Kişiler",
  },
  places: {
    folder: "20_Yerler",
    parentPath: "20_Yerler/20_Yerler.md",
    parentLink: "[[20_Yerler/20_Yerler|Yerler]]",
    parentLabel: "Yerler",
  },
  work: {
    folder: "30_İş",
    parentPath: "30_İş/30_İş.md",
    parentLink: "[[30_İş/30_İş|İş]]",
    parentLabel: "İş",
  },
  tech: {
    folder: "40_Teknoloji",
    parentPath: "40_Teknoloji/40_Teknoloji.md",
    parentLink: "[[40_Teknoloji/40_Teknoloji|Teknoloji]]",
    parentLabel: "Teknoloji",
  },
  routines: {
    folder: "50_Rutinler",
    parentPath: "50_Rutinler/50_Rutinler.md",
    parentLink: "[[50_Rutinler/50_Rutinler|Rutinler]]",
    parentLabel: "Rutinler",
  },
  learning: {
    folder: "60_Öğrenme",
    parentPath: "60_Öğrenme/60_Öğrenme.md",
    parentLink: "[[60_Öğrenme/60_Öğrenme|Öğrenme]]",
    parentLabel: "Öğrenme",
  },
  life: {
    folder: "70_Yaşam",
    parentPath: "70_Yaşam/70_Yaşam.md",
    parentLink: "[[70_Yaşam/70_Yaşam|Yaşam]]",
    parentLabel: "Yaşam",
  },
};

function yamlString(value) {
  return JSON.stringify(String(value ?? ""));
}

function safeFileName(value) {
  let name = String(value ?? "")
    .replace(/[<>:"/\\|?*\x00-\x1F]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/[. ]+$/g, "");

  if (!name) name = "Yeni Not";
  if (/^(con|prn|aux|nul|com[1-9]|lpt[1-9])$/i.test(name)) {
    name = `Not - ${name}`;
  }
  return name.slice(0, 80).trim();
}

function buildFrontmatter(properties) {
  const lines = ["---"];
  for (const [key, value] of Object.entries(properties)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) {
      lines.push(`${key}:`);
      for (const item of value) lines.push(`  - ${yamlString(item)}`);
    } else if (typeof value === "boolean" || typeof value === "number") {
      lines.push(`${key}: ${value}`);
    } else {
      lines.push(`${key}: ${yamlString(value)}`);
    }
  }
  lines.push("---", "");
  return lines.join("\n");
}

class AtomikFormModal extends Modal {
  constructor(app, config, onSubmit) {
    super(app);
    this.config = config;
    this.onSubmit = onSubmit;
    this.values = {};
  }

  onOpen() {
    const { contentEl, modalEl } = this;
    modalEl.addClass("atomik-hizli-ekle-modal");
    contentEl.empty();
    contentEl.createEl("h2", { text: this.config.title });
    if (this.config.description) {
      contentEl.createEl("p", {
        text: this.config.description,
        cls: "setting-item-description",
      });
    }

    let firstInput = null;
    for (const field of this.config.fields) {
      const setting = new Setting(contentEl).setName(field.label);
      if (field.help) setting.setDesc(field.help);

      if (field.type === "textarea") {
        setting.addTextArea((component) => {
          component.setPlaceholder(field.placeholder || "");
          component.inputEl.rows = field.rows || 4;
          component.inputEl.addClass("atomik-wide-input");
          component.onChange((value) => (this.values[field.key] = value));
          this.values[field.key] = field.default || "";
          component.setValue(this.values[field.key]);
          if (!firstInput) firstInput = component.inputEl;
        });
      } else if (field.type === "dropdown") {
        setting.addDropdown((component) => {
          if (field.options) {
            for (const opt of field.options) {
              component.addOption(opt.value, opt.label);
            }
          }
          component.onChange((value) => (this.values[field.key] = value));
          this.values[field.key] = field.default || (field.options && field.options.length ? field.options[0].value : "");
          component.setValue(this.values[field.key]);
          if (!firstInput) firstInput = component.selectEl;
        });
      } else {
        setting.addText((component) => {
          component.setPlaceholder(field.placeholder || "");
          component.inputEl.addClass("atomik-wide-input");
          component.onChange((value) => (this.values[field.key] = value));
          this.values[field.key] = field.default || "";
          component.setValue(this.values[field.key]);
          if (!firstInput) firstInput = component.inputEl;
          component.inputEl.addEventListener("keydown", (event) => {
            if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
              event.preventDefault();
              this.submit();
            }
          });
        });
      }
    }

    const buttons = contentEl.createDiv({ cls: "atomik-form-buttons" });
    const cancel = buttons.createEl("button", { text: "İptal" });
    cancel.addEventListener("click", () => this.close());
    const submit = buttons.createEl("button", {
      text: this.config.submitText || "Oluştur",
      cls: "mod-cta",
    });
    submit.addEventListener("click", () => this.submit());

    window.setTimeout(() => firstInput?.focus(), 30);
  }

  async submit() {
    const missing = this.config.fields.find(
      (field) => field.required && !String(this.values[field.key] || "").trim()
    );
    if (missing) {
      new Notice(`“${missing.label}” alanı boş bırakılamaz.`);
      return;
    }

    const values = { ...this.values };
    this.close();
    await this.onSubmit(values);
  }

  onClose() {
    this.contentEl.empty();
  }
}

class AtomikMenuModal extends SuggestModal {
  constructor(app, items) {
    super(app);
    this.items = items;
    this.setPlaceholder("Oluşturmak istediğin kayıt türünü seç");
  }

  getSuggestions(query) {
    const normalized = query.toLocaleLowerCase("tr-TR");
    return this.items.filter((item) =>
      item.label.toLocaleLowerCase("tr-TR").includes(normalized)
    );
  }

  renderSuggestion(item, el) {
    el.createEl("div", { text: item.label, cls: "atomik-menu-title" });
    if (item.description) {
      el.createEl("small", {
        text: item.description,
        cls: "atomik-menu-description",
      });
    }
  }

  onChooseSuggestion(item) {
    item.run();
  }
}

module.exports = class AtomikHizliEklePlugin extends Plugin {
  async onload() {
    this.addRibbonIcon("zap", "Hızlı Ekle", () => this.openMainMenu());

    this.addCommand({
      id: "hizli-ekle-menu",
      name: "Hızlı Ekle Menüsü",
      callback: () => this.openMainMenu(),
    });

    this.addCommand({
      id: "hizli-yakala",
      name: "Hızlı Yakala",
      callback: () => this.quickCapture(),
    });

    this.addCommand({ id: "yeni-fikir", name: "Yeni Fikir", callback: () => this.newIdea() });
    this.addCommand({ id: "yeni-kisi", name: "Yeni Kişi", callback: () => this.newPerson() });
    this.addCommand({ id: "yeni-yer", name: "Yeni Yer", callback: () => this.newPlace() });
    this.addCommand({ id: "yeni-is-bilgisi", name: "Yeni İş Bilgisi", callback: () => this.newWorkNote() });
    this.addCommand({ id: "yeni-teknoloji-notu", name: "Yeni Teknoloji Notu", callback: () => this.newTechNote() });
    this.addCommand({ id: "yeni-rutin", name: "Yeni Rutin", callback: () => this.newRoutine() });
    this.addCommand({ id: "yeni-ogrenme-notu", name: "Yeni Öğrenme Notu", callback: () => this.newLearningNote() });
    this.addCommand({ id: "yeni-yasam-notu", name: "Yeni Yaşam Notu", callback: () => this.newLifeNote() });
    this.addCommand({ id: "kelime-ekle", name: "Kelime Ekle", callback: () => this.addVocab() });
    this.addCommand({ id: "alisverise-ekle", name: "Alışverişe Ekle", callback: () => this.addShopping() });
    this.addCommand({ id: "gelen-kutusunu-isle", name: "Gelen Kutusunu İşle", callback: () => this.processInbox() });
  }

  openMainMenu() {
    new AtomikMenuModal(this.app, [
      {
        label: "⚡ Hızlı Yakala",
        description: "Tek satırlık notu Gelen Kutusu'na ekler; ekranı değiştirmez.",
        run: () => this.quickCapture(),
      },
      {
        label: "💡 Yeni Fikir",
        description: "Başlık ve açıklama ile ayrı bir fikir sayfası oluşturur.",
        run: () => this.newIdea(),
      },
      {
        label: "👤 Yeni Kişi",
        description: "Ad, ilişki ve kısa notla Kişiler alanına ekler.",
        run: () => this.newPerson(),
      },
      {
        label: "📍 Yeni Yer",
        description: "Kategori ve harita bağlantısıyla Yerler alanına ekler.",
        run: () => this.newPlace(),
      },
      {
        label: "🛠️ Yeni İş Bilgisi",
        description: "İş alanı ve açıklamayla İş bölümüne ekler.",
        run: () => this.newWorkNote(),
      },
      {
        label: "💻 Yeni Teknoloji Notu",
        description: "Teknoloji adı ve açıklamayla Teknoloji bölümüne ekler.",
        run: () => this.newTechNote(),
      },
      {
        label: "🔁 Yeni Rutin",
        description: "Saat ve açıklamayla Rutinler bölümüne ekler.",
        run: () => this.newRoutine(),
      },
      {
        label: "📚 Yeni Öğrenme Notu",
        description: "Başlık, kategori ve açıklamayla Öğrenme bölümüne ekler.",
        run: () => this.newLearningNote(),
      },
      {
        label: "🏠 Yeni Yaşam Notu",
        description: "Başlık, kategori ve açıklamayla Yaşam bölümüne ekler.",
        run: () => this.newLifeNote(),
      },
      {
        label: "🧠 Kelime Ekle",
        description: "İngilizce veya Türkçe kelime defterine yeni kelime ekler.",
        run: () => this.addVocab(),
      },
      {
        label: "🛒 Alışverişe Ekle",
        description: "Satın alınacaklar listesine yeni ürün ekler.",
        run: () => this.addShopping(),
      },
      {
        label: "📤 Gelen Kutusunu İşle",
        description: "Gelen kutusundaki notları ilgili alanlara taşır.",
        run: () => this.processInbox(),
      },
    ]).open();
  }

  quickCapture() {
    new AtomikFormModal(
      this.app,
      {
        title: "⚡ Hızlı Yakala",
        description: "Fikri yaz. Ayrı bir not olarak Gelen Kutusu'na eklenir; tarih ve saat gösterilmez.",
        submitText: "Kaydet",
        fields: [
          {
            key: "text",
            label: "Not",
            placeholder: "Örneğin: Fotoğrafları otomatik gruplandıran uygulama fikri",
            required: true,
          },
        ],
      },
      async ({ text }) => {
        const fullText = text.trim();
        const title = safeFileName(fullText.slice(0, 70));
        await this.createRelatedNote({
          target: TARGETS.inbox,
          title,
          properties: {
            "tür": "hızlı-not",
            "üst-sayfa": TARGETS.inbox.parentLink,
            "ana-sayfa": VAULT_HOME,
            "tags": ["gelen-kutusu"],
          },
          body: fullText,
          open: false,
        });
      }
    ).open();
  }

  newIdea() {
    this.openForm({
      title: "💡 Yeni Fikir",
      fields: [
        { key: "title", label: "Başlık", placeholder: "Fikrin kısa adı", required: true },
        { key: "description", label: "Açıklama", type: "textarea", placeholder: "Fikri birkaç cümleyle açıkla", required: true },
      ],
      target: TARGETS.inbox,
      type: "fikir",
      properties: () => ({ tags: ["gelen-kutusu", "fikir"] }),
      body: (v) => v.description,
    });
  }

  newPerson() {
    this.openForm({
      title: "👤 Yeni Kişi",
      fields: [
        { key: "title", label: "Ad", placeholder: "Ad Soyad", required: true },
        { key: "relation", label: "İlişki", placeholder: "Akraba, arkadaş, iş arkadaşı..." },
        { key: "description", label: "Kısa not", type: "textarea", placeholder: "Hatırlamak istediğin bilgi" },
      ],
      target: TARGETS.people,
      type: "kişi",
      properties: (v) => ({ ilişki: v.relation, tags: ["kişi"] }),
      body: (v) => v.description,
    });
  }

  newPlace() {
    this.openForm({
      title: "📍 Yeni Yer",
      fields: [
        { key: "title", label: "Yer adı", placeholder: "Mekân veya konum adı", required: true },
        { key: "category", label: "Kategori", placeholder: "Gezilecek yer, restoran, iş yeri..." },
        { key: "map", label: "Google Maps bağlantısı", placeholder: "https://maps.google.com/..." },
        { key: "description", label: "Kısa not", type: "textarea", placeholder: "Neden kaydettiğini yaz" },
      ],
      target: TARGETS.places,
      type: "yer",
      properties: (v) => ({ kategori: v.category, harita: v.map, tags: ["yer"] }),
      body: (v) => v.description,
    });
  }

  newWorkNote() {
    this.openForm({
      title: "🛠️ Yeni İş Bilgisi",
      fields: [
        { key: "title", label: "Başlık", placeholder: "Örneğin: A330 trim air valve değişimi", required: true },
        { key: "area", label: "Alan", placeholder: "A330, kabin içi, hat bakım..." },
        { key: "description", label: "Açıklama", type: "textarea", placeholder: "İş sırasında tekrar kullanacağın bilgi", required: true },
      ],
      target: TARGETS.work,
      type: "iş-referansı",
      properties: (v) => ({ alan: v.area, tags: ["iş"] }),
      body: (v) => v.description,
    });
  }

  newTechNote() {
    this.openForm({
      title: "💻 Yeni Teknoloji Notu",
      fields: [
        { key: "title", label: "Başlık", placeholder: "Notun kısa adı", required: true },
        { key: "technology", label: "Teknoloji", placeholder: "Flutter, Excel VBA, Android..." },
        { key: "description", label: "Açıklama", type: "textarea", placeholder: "Komut, çözüm veya açıklama", required: true },
      ],
      target: TARGETS.tech,
      type: "teknoloji-notu",
      properties: (v) => ({ teknoloji: v.technology, tags: ["teknoloji"] }),
      body: (v) => v.description,
    });
  }

  newRoutine() {
    this.openForm({
      title: "🔁 Yeni Rutin",
      fields: [
        { key: "title", label: "Başlık", placeholder: "Rutinin adı", required: true },
        { key: "time", label: "Saat", placeholder: "Örneğin: 07:30 veya Vardiya öncesi" },
        { key: "description", label: "Açıklama", type: "textarea", placeholder: "Tekrarlanan adımlar veya hatırlatmalar" },
      ],
      target: TARGETS.routines,
      type: "rutin",
      properties: (v) => ({ saat: v.time, tags: ["rutin"] }),
      body: (v) => v.description,
    });
  }

  newLearningNote() {
    this.openForm({
      title: "📚 Yeni Öğrenme Notu",
      fields: [
        { key: "title", label: "Başlık", placeholder: "Notun kısa adı", required: true },
        { key: "category", label: "Kategori", placeholder: "Tarih, Biyoloji, Yazılım..." },
        { key: "description", label: "Açıklama", type: "textarea", placeholder: "Öğrendiklerini yaz", required: true },
      ],
      target: TARGETS.learning,
      type: "öğrenme-notu",
      properties: (v) => ({ kategori: v.category, tags: ["öğrenme"] }),
      body: (v) => v.description,
    });
  }

  newLifeNote() {
    this.openForm({
      title: "🏠 Yeni Yaşam Notu",
      fields: [
        { key: "title", label: "Başlık", placeholder: "Notun kısa adı", required: true },
        { key: "category", label: "Kategori", placeholder: "Ev, Araba, Sağlık..." },
        { key: "description", label: "Açıklama", type: "textarea", placeholder: "Notun detayı", required: true },
      ],
      target: TARGETS.life,
      type: "yaşam-notu",
      properties: (v) => ({ kategori: v.category, tags: ["yaşam"] }),
      body: (v) => v.description,
    });
  }

  addVocab() {
    new AtomikFormModal(
      this.app,
      {
        title: "🧠 Kelime Ekle",
        fields: [
          { key: "lang", label: "Dil", type: "dropdown", options: [{label: "İngilizce", value: "İngilizce"}, {label: "Türkçe", value: "Türkçe"}], required: true },
          { key: "word", label: "Kelime", placeholder: "Eklenecek kelime", required: true },
          { key: "meaning", label: "Anlam", placeholder: "Kelimenin anlamı", required: true },
          { key: "example", label: "Örnek cümle", placeholder: "Cümle içinde kullanımı", required: false },
        ],
      },
      async (values) => {
        const fileName = `${values.lang} Kelimeler`;
        const path = `60_Öğrenme/${fileName}.md`;
        let file = this.app.vault.getAbstractFileByPath(path);
        
        const escapeTable = (str) => String(str || "").replace(/\|/g, "\\|").replace(/\n/g, " ");
        const word = escapeTable(values.word);
        const meaning = escapeTable(values.meaning);
        const example = escapeTable(values.example);
        const row = `| ${word} | ${meaning} | ${example} |`;

        if (!file) {
          const content = [
            "---",
            "tür: kelime-listesi",
            "tags:",
            "  - öğrenme",
            "  - kelime",
            `üst-sayfa: ${TARGETS.learning.parentLink}`,
            `ana-sayfa: ${VAULT_HOME}`,
            "---",
            "",
            `# ${fileName}`,
            "",
            "| Kelime | Anlam | Örnek cümle |",
            "|---|---|---|",
            row,
            "",
            `---\n⬆ ${TARGETS.learning.parentLink} · 🏠 ${VAULT_HOME}`,
            ""
          ].join("\n");
          await this.ensureFolder("60_Öğrenme");
          file = await this.app.vault.create(path, content);
          const link = `[[60_Öğrenme/${fileName}|${fileName}]]`;
          await this.updateParentRelations(TARGETS.learning, link);
          new Notice(`Kelime dosyası oluşturuldu ve "${values.word}" eklendi.`);
        } else {
          let content = await this.app.vault.read(file);
          if (content.includes(`| ${word} |`)) {
            new Notice(`"${values.word}" kelimesi zaten mevcut.`);
            return;
          }
          const tableHeader = "|---|---|---|";
          const insertIdx = content.indexOf(tableHeader);
          if (insertIdx !== -1) {
            const afterHeader = insertIdx + tableHeader.length;
            content = content.slice(0, afterHeader) + "\n" + row + content.slice(afterHeader);
          } else {
            content += `\n${row}\n`;
          }
          await this.app.vault.modify(file, content);
          new Notice(`"${values.word}" kelimesi listeye eklendi.`);
        }
      }
    ).open();
  }

  addShopping() {
    new AtomikFormModal(
      this.app,
      {
        title: "🛒 Alışverişe Ekle",
        fields: [
          { key: "item", label: "Ürün adı", placeholder: "Ne alınacak?", required: true },
          { key: "category", label: "Kategori", placeholder: "Gıda, Teknoloji...", required: false },
          { key: "budget", label: "Tahmini bütçe", placeholder: "Miktar", required: false },
          { key: "notes", label: "Not", placeholder: "Nereden alınacak veya detay", required: false },
        ],
      },
      async (values) => {
        const fileName = "Satın Alınacaklar";
        const path = `70_Yaşam/${fileName}.md`;
        let file = this.app.vault.getAbstractFileByPath(path);
        
        const parts = [values.item.trim()];
        if (values.category?.trim()) parts.push(values.category.trim());
        if (values.budget?.trim()) parts.push(values.budget.trim());
        if (values.notes?.trim()) parts.push(values.notes.trim());
        const row = `- [ ] ${parts.join(" — ")}`;

        if (!file) {
          const content = [
            "---",
            "tür: alışveriş-listesi",
            "tags:",
            "  - yaşam",
            "  - alışveriş",
            `üst-sayfa: ${TARGETS.life.parentLink}`,
            `ana-sayfa: ${VAULT_HOME}`,
            "---",
            "",
            `# ${fileName}`,
            "",
            row,
            "",
            `---\n⬆ ${TARGETS.life.parentLink} · 🏠 ${VAULT_HOME}`,
            ""
          ].join("\n");
          await this.ensureFolder("70_Yaşam");
          file = await this.app.vault.create(path, content);
          const link = `[[70_Yaşam/${fileName}|${fileName}]]`;
          await this.updateParentRelations(TARGETS.life, link);
          new Notice(`Alışveriş listesi oluşturuldu ve ürün eklendi.`);
        } else {
          let content = await this.app.vault.read(file);
          if (content.includes(`- [ ] ${values.item.trim()} `) || content.includes(`- [ ] ${values.item.trim()}\n`) || content.endsWith(`- [ ] ${values.item.trim()}`)) {
             new Notice(`"${values.item}" zaten listede var.`);
             return;
          }
          const titleLine = `# ${fileName}`;
          const insertIdx = content.indexOf(titleLine);
          if (insertIdx !== -1) {
            const afterTitle = insertIdx + titleLine.length;
            content = content.slice(0, afterTitle) + "\n\n" + row + content.slice(afterTitle);
          } else {
            content += `\n${row}\n`;
          }
          await this.app.vault.modify(file, content);
          new Notice(`"${values.item}" alışveriş listesine eklendi.`);
        }
      }
    ).open();
  }

  processInbox() {
    const inboxFolder = this.app.vault.getAbstractFileByPath(TARGETS.inbox.folder);
    if (!inboxFolder) {
      new Notice("Gelen kutusu bulunamadı!");
      return;
    }
    const files = inboxFolder.children.filter(f => f.extension === "md" && f.path !== TARGETS.inbox.parentPath);
    if (files.length === 0) {
      new Notice("Gelen kutusu boş!");
      return;
    }

    const items = files.map(file => ({
      label: file.basename,
      description: "Gelen kutusunda",
      run: () => {
        const targets = Object.values(TARGETS).filter(t => t.folder !== TARGETS.inbox.folder).map(t => ({
          label: t.parentLabel,
          description: `Notu ${t.parentLabel} alanına taşı`,
          run: async () => {
            const oldLink = `[[${file.path.replace(/\.md$/i, "")}|${file.basename}]]`;
            const safeTitle = safeFileName(file.basename);
            const newPath = await this.getUniquePath(t.folder, safeTitle);
            const newLink = `[[${newPath.replace(/\.md$/i, "")}|${safeTitle}]]`;
            
            await this.app.fileManager.processFrontMatter(file, (fm) => {
              fm["üst-sayfa"] = t.parentLink;
              if (fm["durum"]) delete fm["durum"];
            });

            await this.app.fileManager.renameFile(file, newPath);
            await this.removeParentRelations(TARGETS.inbox, oldLink, newLink);
            await this.updateParentRelations(t, newLink);
            new Notice(`${safeTitle}, ${t.parentLabel} alanına taşındı.`);
          }
        }));
        new AtomikMenuModal(this.app, targets).open();
      }
    }));
    new AtomikMenuModal(this.app, items).open();
  }

  async removeParentRelations(target, oldLink, newLink) {
    const parent = this.app.vault.getAbstractFileByPath(target.parentPath);
    if (!parent || parent.extension !== "md") return;

    await this.app.fileManager.processFrontMatter(parent, (frontmatter) => {
      if (Array.isArray(frontmatter["alt-sayfalar"])) {
        frontmatter["alt-sayfalar"] = frontmatter["alt-sayfalar"].filter(l => l !== oldLink && l !== newLink);
      }
    });

    let content = await this.app.vault.read(parent);
    content = content.split('\n').filter(line => line.trim() !== `- ${oldLink}` && line.trim() !== `- ${newLink}`).join('\n');
    await this.app.vault.modify(parent, content);
  }

  openForm(config) {
    new AtomikFormModal(
      this.app,
      {
        title: config.title,
        fields: config.fields,
      },
      async (values) => {
        const title = values.title.trim();
        await this.createRelatedNote({
          target: config.target,
          title,
          properties: {
            "tür": config.type,
            ...(config.properties(values) || {}),
            "üst-sayfa": config.target.parentLink,
            "ana-sayfa": VAULT_HOME,
          },
          body: config.body(values) || "",
          open: true,
        });
      }
    ).open();
  }

  async createRelatedNote({ target, title, properties, body, open }) {
    const safeTitle = safeFileName(title);
    await this.ensureFolder(target.folder);
    const path = await this.getUniquePath(target.folder, safeTitle);
    const displayTitle = safeTitle;
    const link = `[[${path.replace(/\.md$/i, "")}|${displayTitle}]]`;

    const navigation = `---\n⬆ ${target.parentLink} · 🏠 ${VAULT_HOME}`;
    const content = [
      buildFrontmatter(properties),
      `# ${displayTitle}`,
      "",
      String(body || "").trim(),
      "",
      navigation,
      "",
    ]
      .join("\n")
      .replace(/\n{4,}/g, "\n\n\n");

    const file = await this.app.vault.create(path, content);
    await this.updateParentRelations(target, link);

    if (open) {
      const leaf = this.app.workspace.getLeaf(true);
      await leaf.openFile(file);
    }

    new Notice(`${displayTitle} kaydedildi.`);
    return file;
  }

  async ensureFolder(folderPath) {
    const normalized = normalizePath(folderPath);
    if (this.app.vault.getAbstractFileByPath(normalized)) return;

    const parts = normalized.split("/");
    let current = "";
    for (const part of parts) {
      current = current ? `${current}/${part}` : part;
      if (!this.app.vault.getAbstractFileByPath(current)) {
        await this.app.vault.createFolder(current);
      }
    }
  }

  async getUniquePath(folder, title) {
    let index = 1;
    let candidate = normalizePath(`${folder}/${title}.md`);
    while (this.app.vault.getAbstractFileByPath(candidate)) {
      index += 1;
      candidate = normalizePath(`${folder}/${title} (${index}).md`);
    }
    return candidate;
  }

  async updateParentRelations(target, link) {
    const parent = this.app.vault.getAbstractFileByPath(target.parentPath);
    if (!parent || parent.extension !== "md") {
      new Notice(`${target.parentLabel} ana sayfası bulunamadı; not oluşturuldu fakat üst liste güncellenemedi.`);
      return;
    }

    await this.app.fileManager.processFrontMatter(parent, (frontmatter) => {
      const current = Array.isArray(frontmatter["alt-sayfalar"])
        ? frontmatter["alt-sayfalar"]
        : frontmatter["alt-sayfalar"]
          ? [frontmatter["alt-sayfalar"]]
          : [];
      if (!current.includes(link)) current.push(link);
      frontmatter["alt-sayfalar"] = current;
    });

    let content = await this.app.vault.read(parent);
    if (content.includes(`- ${link}`)) return;

    const startMarker = "<!-- ATOMIK-RELATIONS:START -->";
    const endMarker = "<!-- ATOMIK-RELATIONS:END -->";
    const start = content.indexOf(startMarker);
    const end = content.indexOf(endMarker);

    if (start !== -1 && end !== -1 && end > start) {
      const block = content.slice(start, end);
      const homeMatch = block.lastIndexOf("\n[[Vault");
      let updatedBlock;
      if (homeMatch !== -1) {
        const beforeHome = block.slice(0, homeMatch).replace(/\s+$/, "");
        const homeAndAfter = block.slice(homeMatch).replace(/^\s*/, "\n\n");
        updatedBlock = `${beforeHome}\n- ${link}${homeAndAfter}`;
      } else {
        updatedBlock = `${block.replace(/\s+$/, "")}\n- ${link}\n`;
      }
      content = content.slice(0, start) + updatedBlock + content.slice(end);
    } else {
      content = `${content.trimEnd()}\n\n${startMarker}\n## Bağlı Notlar\n\n- ${link}\n\n[[Vault|← Ana Sayfa]]\n${endMarker}\n`;
    }

    await this.app.vault.modify(parent, content);
  }
};
