max = float(input())
kol = int(input())
ercon = 0
upcon = 0
maxin = -9999999999
midin = 0
koltrue = 0
for i in range(kol):
    a = input()
    try:
        b = float(a)
        if b > max:
            upcon += 1
        if b > maxin:
            maxin = b
        koltrue += 1
        midin += b
    except:
        ercon += 1
midin = midin/koltrue
print(kol)
print(ercon)
print(upcon)
print(f"{maxin:.1f}")
print(f"{midin:.1f}")
