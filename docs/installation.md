# Instalación y solución de problemas

[Volver al README](../README.md)

## Instalación

| Herramienta | Requisito |
| --- | --- |
| Git | Para clonar |
| Python | **3.11 o 3.12** (3.13 no está soportado) |
| Node.js | **20 o posterior**, con `npm` |
| Docker y Compose | Opcional; alternativa al instalador nativo |

```bash
git clone https://github.com/EnriqueForte/MetaTracer.git
cd MetaTracer
```

### Windows

Python 3.12 y Node LTS, si faltan:

```powershell
winget install Python.Python.3.12 OpenJS.NodeJS.LTS Git.Git
```

```powershell
.\install.cmd
.\MetaTracer.cmd
```

`install.cmd` y `MetaTracer.cmd` también se abren con doble clic.

### Linux (Debian / Parrot)

```bash
chmod +x install.sh run.sh    # o: bash install.sh
./install.sh
./run.sh
```

El instalador crea `.venv`, instala el paquete Python y la Web UI (`npm ci`),
y copia `.env.example` → `.env` si aún no existe. **Ctrl+C** detiene la app.

#### Parrot 7 (Python del sistema = 3.13)

Apt **no** ofrece `python3.11` ni `python3.11-venv`. Si ya tienes Python 3.11 en `~/.local` (o pyenv), crea el entorno con `virtualenv` y luego ejecuta el instalador. Si `.venv` ya existe, revisa primero su contenido; renómbralo o elimínalo solo si quieres sustituirlo.

```bash
sudo apt install python3-virtualenv python3-pip
python3 -m virtualenv -p "$HOME/.local/bin/python3.11" .venv
./install.sh
```

Si `npm ci` corta con `ETIMEDOUT`, no borres `.venv`. Reintenta solo la UI:

```bash
cd web
export NODE_OPTIONS=--dns-result-order=ipv4first
npm ci
cd ..
./run.sh
```

### Extras de desarrollo

```bash
./install.sh --dev          # Linux
.\install.cmd --dev         # Windows
```

Instala `pytest` y `ruff` además del runtime.

## Arranque

Con el instalador ya ejecutado:

| Sistema | Comando | UI | API |
| --- | --- | --- | --- |
| Windows | `.\MetaTracer.cmd` | [127.0.0.1:3000](http://127.0.0.1:3000) | [127.0.0.1:8000](http://127.0.0.1:8000) |
| Linux / Parrot | `./run.sh` | igual | igual |

Mantén la terminal abierta. En una VM, abre esas URLs en el navegador de la VM.

Un overlay rojo de hidratación en Next.js con atributos `data-darkreader-*`
lo provoca **Dark Reader** (u otra extensión que reescribe el HTML). No es un
fallo de MetaTracer: desactívala en `127.0.0.1` o ignora el overlay. El tema
Sistema / Oscuro / Claro va en la propia UI.
