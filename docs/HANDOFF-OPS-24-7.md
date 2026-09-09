# Handoff — ops site copy + 24/7 hunt (2026-09-09)

**Audience:** Damian  
**Site:** https://mrbinio.github.io/copy-lab-ops/

---

## 1. Executive summary

Firebase console (Hello Damian, lista projektów) **nie jest labem**. To zaplecze Google pod login. Lab to GitHub Pages.

Hunt leci **co godzinę** na GitHub Actions (Mac może być off). Wynik ląduje na zakładce Hunt i w linii statusu na Teraz.

PolyCop pick nadal **Antblack**, dopóki hunt nie przebije 60/90d + conc + CopyGrade. Strona nie włącza copy.

## 2. Changelog

- Zakładka Teraz: krótko co to jest i co znaczy każda zakładka.
- Workflow `.github/workflows/hunt-pages.yml` + `scripts/publish_ops_pages.sh`.

## 3. Next

- Login Google na stronie: jeden nowy projekt Firebase `copy-lab-ops` — nie klikaj istniejących (gym, dive, football).
- Mitch collaborator, gdy będzie GitHub username.
