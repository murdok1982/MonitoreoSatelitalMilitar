# Modelos de Detección — AEGIS-IMINT

## Modelo requerido

Coloca tu modelo YOLOv8 entrenado en este directorio con el nombre:

```
modelos/yolov8_military.pt
```

O bien ajusta la variable `YOLO_MODEL_PATH` en tu archivo `.env`.

---

## Opciones para obtener un modelo

### Opción 1 — YOLOv8 preentrenado (COCO, para pruebas)

```bash
# Instala ultralytics si aún no lo has hecho
pip install ultralytics

# Descarga YOLOv8n preentrenado en COCO (pruebas rápidas)
python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"
# Mueve el archivo descargado:
mv yolov8n.pt modelos/yolov8_military.pt
```

> **Nota**: COCO incluye clases como `car`, `truck`, `bus`, `boat`, `airplane`.
> Para uso táctico real se recomienda un modelo especializado (ver opciones abajo).

---

### Opción 2 — xView Dataset (detección aérea, recomendado)

xView contiene ~60 clases de objetos vistos desde satélite/avión, incluyendo
vehículos militares, aviones, barcos y maquinaria pesada.

1. Solicita acceso en: <https://xviewdataset.org/>
2. Descarga las imágenes y etiquetas
3. Entrena con Ultralytics:

```bash
yolo detect train data=xview.yaml model=yolov8m.pt epochs=100 imgsz=640
```

---

### Opción 3 — DOTA Dataset (imágenes de satélite orientadas)

DOTA incluye 15 categorías de objetos aéreos con anotaciones OBB (Oriented Bounding Box).

1. Descarga en: <https://captain-whu.github.io/DOTA/dataset.html>
2. Convierte anotaciones con `dota2yolo` y entrena:

```bash
yolo obb train data=dota8.yaml model=yolov8m-obb.pt epochs=50
```

---

### Opción 4 — Modelos públicos en HuggingFace

Busca modelos preentrenados para detección satelital:

```
https://huggingface.co/models?search=satellite+detection+yolo
```

---

## Clases militares soportadas

El detector filtra automáticamente por las siguientes clases (insensible a mayúsculas):

| Clase | Descripción |
|-------|-------------|
| `vehicle` / `military vehicle` | Vehículos genéricos / militares |
| `tank` | Carro de combate |
| `armored vehicle` | Vehículo blindado |
| `truck` / `cargo truck` | Camión de transporte |
| `engineering vehicle` | Vehículo de ingeniería |
| `ground track vehicle` | Vehículo oruga terrestre |
| `helicopter` / `aircraft` | Aeronaves |
| `fixed-wing aircraft` | Avión de ala fija |
| `ship` / `boat` | Embarcaciones |

Si ninguna clase coincide, se reportan todas las detecciones (modo genérico).

---

## Umbral de confianza

Ajusta `CONFIDENCE_THRESHOLD` en `.env` (por defecto `0.45`).
Valores más altos = menos falsos positivos pero más falsos negativos.
