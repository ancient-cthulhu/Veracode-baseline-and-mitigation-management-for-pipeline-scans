# Veracode CI Templates

[English](README.md) | **Español**

Workflow reutilizable de GitHub Actions para Veracode Pipeline Scan con gestión centralizada de baselines por rama.

La rama por defecto de cada repositorio consumidor es la baseline de seguridad. Cada push a esa rama actualiza las baselines almacenadas. Cualquier otra rama o pull request se escanea como delta contra esas baselines, de modo que el build solo falla por los hallazgos que el cambio ha introducido realmente.

## Por qué

Pipeline Scan no guarda estado. En una aplicación existente, el primer escaneo devuelve un backlog de hallazgos que nadie ha introducido hoy, así que un gate simple de "fallar ante High" rompe todas las pull requests y los equipos acaban desactivándolo.

Una baseline filtra los hallazgos conocidos y solo bloquea por los nuevos. La regla pasa a ser **"no empeorar"**:

- Los desarrolladores solo corrigen lo que introduce su cambio.
- El gate puede ser bloqueante desde el primer día, incluso con deuda existente.
- La deuda existente se sigue gestionando y remediando mediante policy scans y mitigaciones en la plataforma Veracode, no en cada pull request.

Las baselines solo se generan desde la rama baseline, se guardan en un repositorio separado en el que solo escribe CI, y cada actualización es un commit de git. Una rama de funcionalidad no puede meter sus propios hallazgos en la baseline, y todo cambio queda auditado.

## El modelo

| Evento | Modo | Qué ocurre |
|---|---|---|
| Push a la rama baseline | `baseline` | Reescanea y sobrescribe las baselines almacenadas. Nunca bloquea |
| Pull request / push a cualquier otra rama | `delta` | Escanea contra las baselines y bloquea por hallazgos nuevos |
| `workflow_dispatch` o `schedule` semanal en la rama baseline | `baseline` | Actualización bajo demanda o semanal (recoge mitigaciones aprobadas recientemente) |

Las baselines se indexan por la **rama baseline**, nunca por la rama en ejecución, así que todas las ramas y pull requests se comparan contra la misma fuente de verdad.

```
baselines/<owner>_<repo>/<rama-baseline>/<nombre-fichero-artefacto>/
  ├── baseline.json                     # resultados completos del escaneo
  └── baseline-mitigated-findings.json  # solo mitigaciones aprobadas
```

## Inicio rápido

1. Añade los [secretos](#secretos).
2. Copia [`examples/veracode.yml`](examples/veracode.yml) en `.github/workflows/veracode.yml` y ajusta la rama del push a tu rama por defecto. Llamador mínimo:

   ```yaml
   on:
     push:
       branches: [main]
     pull_request:
     workflow_dispatch:

   permissions:
     contents: read

   jobs:
     veracode:
       uses: Veracode-CSE-Demos/veracode-ci-templates/.github/workflows/veracode-pipeline.yml@main
       secrets: inherit
   ```

3. Ejecuta el workflow una vez en la rama por defecto con `mode: baseline`. Hasta entonces, los escaneos delta muestran `No baseline` y pasan (salvo con `strict_baselines: true`).
4. Marca el job de Veracode como **status check obligatorio** en la rama por defecto.

**Usar tu propia copia (recomendado en producción):** haz un fork de este repo y configura `templates_repo` (debe coincidir con el repo de `uses:`) y `baseline_repo` (puede ser un repo privado separado).

## Tipos de baseline

| `baseline_type` | Compara contra | Hace fallar el build por | Requiere app name | Escaneos por artefacto |
|---|---|---|---|---|
| `full` (por defecto) | `baseline.json` | Solo hallazgos nuevos | No | 1 |
| `mitigated` | `baseline-mitigated-findings.json` | Cualquier hallazgo no mitigado, antiguo o nuevo | Sí | 1 |
| `both` | Ambos ficheros | Fallo en cualquiera de las dos comparaciones | Sí | 2 |

- **`full`**: el gate delta. Úsalo en aplicaciones con deuda existente. Es la opción habitual.
- **`mitigated`**: un gate de estilo política, no un gate delta. Solo se suprimen los hallazgos con mitigación **aprobada** en la plataforma Veracode (las propuestas se ignoran). Lo genera [`vcpipemit.py`](https://github.com/veracode/veracode-pipeline-mitigation), emparejando por CWE, fichero y línea (±3 líneas). Úsalo en aplicaciones maduras donde todo lo que no esté aceptado formalmente debe bloquear. Requiere un policy scan completado en el perfil de aplicación.
- **`both`**: muestra ambas vistas en el resumen. Bloquea con la misma exigencia que `mitigated`. Útil para migrar de `full` a `mitigated`.

Si hay app name configurado, las ejecuciones baseline siempre generan ambos ficheros, así que puedes cambiar de tipo más adelante sin una nueva actualización.

## Parámetros de entrada

| Parámetro | Por defecto | Propósito |
|---|---|---|
| `mode` | `auto` | `auto`, `baseline` o `delta`. `delta` en la rama baseline prueba el gate sin sobrescribir |
| `baseline_branch` | rama por defecto del repo | Rama propietaria de las baselines (por ejemplo `develop` en GitFlow) |
| `baseline_repo` | `Veracode-CSE-Demos/veracode-ci-templates` | Repositorio donde se guardan las baselines |
| `baseline_store_branch` | rama por defecto del almacén | Rama del almacén donde se hace commit de las baselines |
| `baseline_type` | `full` | `full`, `mitigated` o `both` |
| `templates_repo` | `Veracode-CSE-Demos/veracode-ci-templates` | Repo con este workflow. Debe coincidir con `uses:` |
| `fail_on_severity` | `Very High, High` | Severidades que hacen fallar un escaneo delta |
| `fail_on_cwe` | vacío | CWEs que bloquean sea cual sea su severidad, por ejemplo `80` para XSS |
| `policy_name` | vacío | Política de Veracode para evaluar hallazgos. Solo políticas por defecto de Veracode |
| `strict_baselines` | `false` | Falla si un artefacto no tiene baseline. Actívalo cuando todos los repos la tengan |
| `artifacts_glob` | vacío | Escanea artefactos existentes y omite el autopackager. Solo ve ficheros del checkout del repo |
| `package_source` | `.` | Ruta de código para `veracode package` |
| `artifact_extensions` | `jar war ear dll exe nupkg zip tar tgz tar.gz` | Extensiones escaneables |
| `scan_timeout` | `60` | Timeout en minutos |
| `java_version` / `python_version` | `17` / `3.12` | Versiones de las herramientas |
| `runs_on` | `ubuntu-latest` | Etiqueta del runner |
| `upload_results` | `true` | Adjunta los resultados en bruto a la ejecución (14 días) |
| `upload_sarif` | `false` | Publica hallazgos delta en code scanning. Requiere `security-events: write` |
| `source_path_prefix` | vacío | Prefijo para que las rutas SARIF se resuelvan, por ejemplo `src/main/java` |
| `app_name` | vacío | Nombre del perfil de aplicación en Veracode. Prioridad sobre `VERACODE_APP_NAME` |

Las baselines se indexan por **nombre de fichero** del artefacto. Mantén nombres estables (sin versiones ni IDs de build), o cada build dejará de encontrar su baseline.

## Secretos

| Secreto | Obligatorio | Propósito |
|---|---|---|
| `VERACODE_API_ID` / `VERACODE_API_KEY` | sí | Credenciales de API de Veracode |
| `CI_PUSH_TOKEN_VCT` | sí | Token fine grained: lectura en el repo de plantillas, lectura y escritura en el repo de baselines |
| `VERACODE_APP_NAME` | para `mitigated` / `both` | Nombre exacto del perfil de aplicación |

Las credenciales se escriben en `~/.veracode/credentials`, nunca en la línea de comandos. Las pull requests desde forks no reciben secretos y fallan con una explicación; no lo evites con `pull_request_target`.

## Buenas prácticas

- **Haz el check obligatorio.** Si se fusiona una pull request fallida, la siguiente actualización mete sus hallazgos en la baseline.
- **Mantén los policy scans** en la rama baseline. La baseline oculta la deuda en las pull requests por diseño; la plataforma es donde sigue visible.
- **Mantén la actualización semanal** para que la baseline mitigada siga las decisiones de la plataforma.

## Resolución de problemas

| Síntoma | Causa / solución |
|---|---|
| Todos los artefactos muestran `No baseline` | Aún no hay actualización. Ejecuta en la rama baseline con `mode: baseline` |
| Existen baselines pero no se encuentran | Cambió el nombre del artefacto. Revisa la ruta en la tabla "run plan" |
| La baseline mitigada está vacía | Sin policy scan completado, nombre de perfil distinto, o sin mitigaciones `APPROVED` |
| `veracode package` no encuentra nada | El autopackager no puede compilar el proyecto. Corrige el empaquetado o usa `artifacts_glob` |
| No se pueden subir las baselines | El token no tiene escritura en el repo de baselines |

## Estructura del repositorio

```
.github/workflows/veracode-pipeline.yml   workflow reutilizable
.github/workflows/validate.yml            lint y autotest
scripts/                                  helpers de resumen y SARIF
examples/veracode.yml                     plantilla de llamador
baselines/                                almacén de baselines
```

## Referencias

- [Pipeline Scan](https://docs.veracode.com/r/Pipeline_Scan)
- [Parámetros de Pipeline Scan](https://docs.veracode.com/r/r_pipeline_scan_commands)
- [veracode package](https://docs.veracode.com/r/veracode_package)
- [veracode/veracode-pipeline-mitigation](https://github.com/veracode/veracode-pipeline-mitigation)
