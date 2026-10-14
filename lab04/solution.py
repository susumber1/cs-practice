def winner(score):
    minnum = 0
    maxsc = 0
    for i in range(len(score)):
        if score[i] > maxsc:
            maxsc = score[i]
            minnum = i
    return minnum

def average(score):
    sum = 0
    kolv = 0
    for i in range(len(score)):
        sum += score[i]
        kolv += 1
    return sum / kolv

def ranking(score):
    ranksc = sorted(score)
    return ranksc

def above_average(score,n):
    return score(n) > everage(score)