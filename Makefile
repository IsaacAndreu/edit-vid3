# Atajos del día a día. `make help` lista todos.
PYTHON ?= python
PROYECTO ?= materiales/Video1
SALIDA ?= out/$(notdir $(PROYECTO))/$(notdir $(PROYECTO)).mp4

.PHONY: help install doctor test typecheck check video props render report studio clean

help: ## Muestra esta ayuda
	@grep -E '^[a-z]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-10s %s\n", $$1, $$2}'

install: ## Instala dependencias de Python y de Remotion
	$(PYTHON) -m pip install -r requirements.txt
	npm install

doctor: ## Comprueba el entorno (sin llamadas de pago)
	$(PYTHON) main.py doctor $(PROYECTO)

test: ## Tests de Python (sin red)
	$(PYTHON) -m unittest discover -s tests

typecheck: ## Comprueba los tipos de las plantillas
	npm run typecheck

check: test typecheck ## Tests + tipos

video: ## Genera el vídeo de PROYECTO (reanuda si ya había trabajo hecho)
	$(PYTHON) main.py $(PROYECTO)

props: ## Como `video`, pero se detiene antes del render
	$(PYTHON) main.py $(PROYECTO) --skip-render

render: ## Solo render + master + postflight desde los props existentes
	$(PYTHON) main.py render $(SALIDA)

report: ## Regenera el informe HTML del run
	$(PYTHON) main.py report $(SALIDA)

studio: ## Abre Remotion Studio con los props del run
	$(PYTHON) main.py studio $(SALIDA)

clean: ## Lista los assets por run (añade ARGS="--keep 3 --yes" para borrar)
	$(PYTHON) main.py clean $(ARGS)
