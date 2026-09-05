import csv,glob,os
from collections import defaultdict

IDS={'5388944','5153608','5472408','5472409','5130776',
     '5201458','5130768','5130772','5522345','5201465','5192197'}

files=sorted(glob.glob(os.path.expanduser('~/odds_data/snapshots/*.csv')))

def keyline(s):
    return str(s).strip().replace(' ','')

prev={}

for f in files:
    ts=os.path.basename(f).replace('snapshot_','').replace('.csv','')
    cur=defaultdict(list)

    with open(f,encoding='utf-8-sig') as z:
        for r in csv.DictReader(z):
            if r['match_id'] in IDS and r['mty']=='1000':
                cur[r['match_id']].append(
                    (r['market_id'],r['option'],keyline(r['line']),r['odds'])
                )

    for mid,rows in cur.items():
        now={}
        for market,op,line,odds in rows:
            now.setdefault(market,[]).append((op,line,odds))

        # 每场比赛只在 market_id 集合或盘口档位发生变化时输出
        old=prev.get(mid)
        if old is not None:
            old_ids=set(old)
            new_ids=set(now)

            if old_ids != new_ids:
                print('\n',ts,mid,'MARKET_CHANGE')
                print('OLD:',','.join(sorted(old_ids)))
                print('NEW:',','.join(sorted(new_ids)))

                for market in sorted(old_ids ^ new_ids):
                    if market in old:
                        print(' -',market,old[market])
                    if market in now:
                        print(' +',market,now[market])

        prev[mid]=now
