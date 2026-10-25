def parse_line(s):
    s=str(s).strip().replace(" ","")
    if not s:
        return None
    try:
        if "/" in s:
            a,b=s.split("/",1)
            x=float(a)
            y=float(b)
            if not b.startswith(("+","-")):
                y=-abs(y) if x<0 else abs(y)
            return [x,y]
        return [float(s)]
    except:
        return None


def norm(s):
    p=parse_line(s)
    if not p:
        return None

    return {
        "raw":str(s),
        "legs":p,
        "depth":sum(abs(x) for x in p)/len(p)
    }


def compare_line(old,new):
    a=norm(old)
    b=norm(new)

    if not a or not b:
        return {
            "changed":None,
            "direction":"UNKNOWN",
            "change_type":"UNKNOWN",
            "steps":None
        }

    x=a["depth"]
    y=b["depth"]

    if x==y:
        return {
            "changed":False,
            "direction":"SAME",
            "change_type":"SAME",
            "steps":0
        }

    if y>x:
        d="DEEPER"
    else:
        d="SHALLOWER"

    diff=abs(y-x)

    if diff==0.25:
        ct="QUARTER_STEP"
    elif diff==0.5:
        ct="HALF_STEP"
    else:
        ct="MULTI_STEP"

    return {
        "changed":True,
        "direction":d,
        "change_type":ct,
        "steps":diff/0.25
    }


if __name__=="__main__":
    tests=[
        ("-0.5","-0.75"),
        ("-1","-1/1.5"),
        ("-1/1.5","-1"),
        ("+0.5","+0.25"),
        ("+0.25","+0.5"),
        ("0","-0.5"),
        ("-0.5","0"),
        ("0.5","0/0.5"),
        ("0/0.5","0.5"),
        ("1","1/1.5"),
        ("1/1.5","1"),
    ]

    print("=== Asian Line Parser V3.3 ===")

    for old,new in tests:
        r=compare_line(old,new)
        print(
            old,"→",new,
            "|",r
        )
