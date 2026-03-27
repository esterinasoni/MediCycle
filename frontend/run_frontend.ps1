param(
    [int]$Port = 3000
)

python -m http.server $Port
