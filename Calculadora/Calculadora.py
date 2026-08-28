import soma
import subtrai
import multiplicação
import divisão
import resto

n1 = float(input("Digite o primeiro número: "))
n2 = float(input("Digite o segundo número: "))
op = input("Digite um operando: ")

if op == "+":
    resp = soma.somaf(n1,n2)
elif op == "-":
    resp = subtrai.subtraif(n1,n2)
elif op == "*":
    resp = multiplicação.multiplicaf(n1,n2)
elif op == "/":
    resp = divisão.divisaof(n1,n2)
else:
    resp = resto.restof(n1,n2)

print("O resultado é %.2f" %resp)

