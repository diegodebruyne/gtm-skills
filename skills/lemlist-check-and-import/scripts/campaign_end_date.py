#!/usr/bin/env python3
"""Date de fin d'une campagne Lemlist, par simulation jour par jour (controles 26 et 36 du skill).

Hypotheses explicites (a afficher dans le rapport) :
  - envois les jours ouvres du planning uniquement (lundi-vendredi par defaut), jamais les jours feries passes en argument ;
  - capacite = boites conformes x limite par boite et par jour, repartie uniformement ;
  - delais entre emails en jours CALENDAIRES apres l'envoi precedent ; un email du un jour non ouvre part le jour ouvre suivant ;
  - deux politiques de priorite, car Lemlist ne la documente pas : "relances d'abord" (les emails 2 et 3 dus passent avant
    les nouveaux emails 1) et "nouveaux d'abord" (les nouveaux emails 1 passent avant les relances). La date a communiquer
    est la PLUS TARDIVE des deux ; l'ecart entre les deux est l'incertitude.

Usage :
  python campaign_end_date.py --leads 515 --already-sent-step1 35 --sent-date 2026-10-28 --boxes 5 --limit 30 \
      --start 2026-10-29 --delays 4,7 --holidays 2026-11-11
"""
import argparse, datetime as dt, heapq


def simulate(leads, already1, sent_date, cap, start, delays, holidays, weekdays, policy):
    q = []  # (priorite, due, etape, id)
    n = 0
    for i in range(already1):  # emails 1 deja envoyes : leur email 2 est du apres le delai
        heapq.heappush(q, (0, sent_date + dt.timedelta(delays[0]), 2, n)); n += 1
    for i in range(leads - already1):
        heapq.heappush(q, (1, start, 1, n)); n += 1
    day, last, used_days = start, {}, 0
    while q:
        if day.weekday() not in weekdays or day in holidays:
            day += dt.timedelta(1); continue
        due_now = sorted([x for x in q if x[1] <= day], key=lambda x: ((x[2] == 1) if policy == "relances" else (x[2] != 1), x[1], x[3]))
        sent = due_now[:cap]
        if not sent and not any(x[1] <= day for x in q):
            day += dt.timedelta(1); continue
        sset = set(map(lambda x: x[3], sent))
        q = [x for x in q if not (x[3] in sset and x in sent)]
        heapq.heapify(q)
        for pr, due, st, i in sent:
            last[st] = day
            if st < 3:
                heapq.heappush(q, (0, day + dt.timedelta(delays[st - 1]), st + 1, i))
        used_days += 1
        day += dt.timedelta(1)
    return last, used_days


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--leads", type=int, required=True)
    ap.add_argument("--already-sent-step1", type=int, default=0)
    ap.add_argument("--sent-date", default=None, help="date des emails 1 deja envoyes (AAAA-MM-JJ)")
    ap.add_argument("--boxes", type=int, required=True)
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--start", required=True, help="premier jour d'envoi a simuler (AAAA-MM-JJ)")
    ap.add_argument("--delays", default="4,7")
    ap.add_argument("--holidays", default="")
    ap.add_argument("--weekdays", default="0,1,2,3,4")
    a = ap.parse_args()
    start = dt.date.fromisoformat(a.start)
    sent_date = dt.date.fromisoformat(a.sent_date) if a.sent_date else start
    delays = [int(x) for x in a.delays.split(",")]
    holidays = {dt.date.fromisoformat(x) for x in a.holidays.split(",") if x}
    weekdays = {int(x) for x in a.weekdays.split(",")}
    cap = a.boxes * a.limit
    print(f"{a.leads} leads, {a.boxes} boites x {a.limit} = {cap} envois par jour ouvre, depart {start:%d/%m/%Y}, delais {delays}, feries {sorted(map(str, holidays))}")
    ends = []
    for pol in ("relances", "nouveaux"):
        last, days = simulate(a.leads, a.already_sent_step1, sent_date, cap, start, delays, holidays, weekdays, pol)
        ends.append(last[3])
        print(f"  politique « {pol} d'abord » : fin emails 1 {last[1]:%a %d/%m} | fin emails 2 {last[2]:%a %d/%m} | FIN email 3 {last[3]:%a %d/%m/%Y} | {days} jours d'envoi")
    print(f"=> date de fin a communiquer (la plus tardive) : {max(ends):%A %d/%m/%Y} ; la plus tot : {min(ends):%d/%m/%Y}")


if __name__ == "__main__":
    main()
