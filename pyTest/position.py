def visio_to_svg(PinX, PinY):
    x = PinX * 72.0 - 7.0867
    y = PinY * 9.078 - 667.608
    return round(x, 3), round(y, 3)

# Contoh
print(visio_to_svg(13.67126, 8.09556))  # (977.244, -594.118)
print(visio_to_svg(12.84449, 8.09556))  # (917.717, -594.118)
print(visio_to_svg(6.171602116511845, 5.527216651579234))  # (977.244, -592.701)