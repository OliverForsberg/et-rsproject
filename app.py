from flask import Flask, render_template, request, redirect, url_for, session
from pysnmp.hlapi import getCmd, nextCmd, SnmpEngine, CommunityData, UdpTransportTarget, ContextData, ObjectType, ObjectIdentity
import sqlite3
from datetime import datetime
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import os

app = Flask(__name__, static_folder = "static")
app.secret_key = "MasoMaso"

Brugere = {
    "Admin": "Admin",
    "Marcus": "Maso" 
}

routers = [
    {"Navn": "Main Router", "Model": "Cisco 1941", "IP": "172.16.0.1", "Community": "mainrouter"},
    {"Navn": "Switch Router", "Model": "Cisco 1941", "IP": "192.168.2.1", "Community": "switch"},
    {"Navn": "Edgerouter 52", "Model": "Edgerouter X", "IP": "192.168.2.2", "Community": "router52"},
    {"Navn": "Edgerouter 3", "Model": "Edgerouter X", "IP": "192.168.2.3", "Community": "router03"},
    {"Navn": "Edgerouter 70", "Model": "Edgerouter X", "IP": "192.168.2.4", "Community": "router70"},
]

def router_info(ip, community="Public"):
    oids = {
        "Uptime":           "1.3.6.1.2.1.1.3.0",
        "Interfaces":       "1.3.6.1.2.1.2.1.0",
        "Lokation":         "1.3.6.1.2.1.1.6.0",
        "Hukommelse":       "1.3.6.1.4.1.9.2.1.8.0",
        "Genstart_årsag":   "1.3.6.1.4.1.9.2.1.2.0",
        "Temp":             "1.3.6.1.4.1.9.9.13.1.3.1.3.1"
    }

    result ={}
    for key, oid in oids.items():
        try:
            iteratior = getCmd(
                SnmpEngine(),
                CommunityData(community),
                UdpTransportTarget((ip, 161), timeout = 2, retries = 1),
                ContextData(),
                ObjectType(ObjectIdentity(oid))
            )
            errorIndication, errorStatus, _, varbinds = next(iterator)
            if errorIndication or errorStatus:
                result[key] = "Ukendt"
            else:
                result[key] = str(varBinds[0][1])
        except Exception:
            result[key] = "Ukendt"
    
    try:
        route_list = route_list_read(ip, community)
        result["Routingtabel"] = ", ".join(route_list) if route_list else "ingen"
    except Exception:
        result["Routingtabel"] = "Ukendt"
    return result

def insert_uptime(router_name, uptime_seconds):
    try:
        conn = sqlite3.connect("uptime_data.db")
        cursor = conn.cursor()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO uptime (router_name, uptime_seconds, timestamp) VALUES (?, ?, ?)",
                       (router_name, uptime_seconds, timestamp))
        conn.commit()
    finally:
        conn.close()

def route_list_read(ip, community):
    route_list = []
    for (errorIndication, errorStatus, _, varBinds) in nextCmd(
        SnmpEngine(),
        CommunityData(community),
        UdpTransportTarget((ip, 161)),
        ContextData(),
        ObjectType(ObjectIdentity("1.3.6.1.2.1.4.21.1.1"))
    ):
        if errorIndication or errorStatus:
            break
        for varBinds in varBinds:
            try:
                ren_data = varBind[1]
                ip_address = ".".join([str(int(byte)) for byte in ren_data.asOctets()])
                route_list.append(ip_address)
            except Exception:
                continue
    return route_list
    
def uptime_graph(router_name, rows):
    timestamps = [datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")for row in rows]
    status = [0.2 if row[1] > 0 else 0 for row in rows]

    graph_filnavn = f"uptime_{router_name}.png"
    graph_filvej = os.path.join("static", graph_filnavn)

    plt.figure(figsize=(12, 6), dpi=300)
    plt.plot(timestamps, status, marker="o", drawstyle="steps-post", linewidth=2)
    plt.title(f"Status for {router_name}", fontsize=14, pad=20)
    plt.xlabel("Tidspunkt", fontsize = 12)
    plt.ylabel("Status (Tændt/slukket)", fontsize = 12)

    plt.ylim(-0.05, 0.25)
    plt.yticks([0, 0.2], ["Slukket", "Tændt"], fontsize = 12)

    plt.grid(True, linestyle = "--", alpha = 0.7)

    dags_dato = datetime.now().date()
    if all(t.date() == dags_dato for t in timestamps):
        plt.gca().xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter("%H:%M"))
    else:
        plt.gca().xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter("%Y-%m-%d %H:%M"))
    
    plt.xticks(rotation = 45, ha="right", fontsize = 10)
    plt.tight_layout()

    plt.savefig(graph_filvej, dpi=300, bbox_inches="tight", pad_inches = 0.2)
    plt.close()
    return graph_filnavn

@app.route("/", methods=["GET", "POST"])
def login():
    if session.get("loggedin"):
        return redirect(url_for("dashboard"))
    
    fejl = None

    if request.method == "POST":
        brugernavn = request.form["brugernavn"]
        kodeord = request.form["kodeord"]
        if brugernavn in Brugere and Brugere[brugernavn] == kodeord:
            session["loggedin"] = True
            session["brugernavn"] = brugernavn
            return redirect(url_for("dashboard"))
        else:
            fejl = "Forkert brugernavn eller kodeord"
    return render_template("login.html", fejl=fejl)

@app.route("/dashboard")
def dashboard():
    if not session.get("loggedin"):
        return redirect(url_for("login"))

    router_data = []
    for r in routers:
        info = router_info(r["IP"], r["Community"])
        uptime_str = info.get("Uptime", "0")
        try:
            uptime_ticktime = int(uptime_str.split()[0])
            uptime_sekunder = uptime_ticktime // 100
            insert_uptime(r["Navn"], uptime_sekunder)

            dage = uptime_sekunder // 86400
            timer = (uptime_sekunder % 86400) // 3600
            minutter = (uptime_sekunder % 3600) // 60
            sekunder = uptime_sekunder % 60
            uptime_final = f"{dage}d {timer}h {minutter}m {sekunder}s"
        except Exception:
            uptime_final = "ukendt"
        
        router_data.append({
            "Navn":     r["Navn"],
            "Model":    r["Model"],
            "IP":       r["IP"],
            "Uptime":   uptime_final,
            "Lokation": info.get("Lokation", "Ukendt")
        })
    return render_template("dashboard.html", routers=router_data)


@app.route("/router/<router_name>")
def router(router_name):
    if not session.get("loggedin"):
        return redirect(url_for("login"))

    r = next((r for r in routers if r["Navn"] == router_name), None)
    if not r:
        return "Router ikke fundet", 404
    
    info = router_info(r["IP"], r["Community"])

    conn = sqlite3.connect("uptime_data.db")
    cursor = conn.cursor()
    cursor.execute("""
        WITH time_groups AS (
            SELECT
                timestamp,
                uptime_seconds,
                strftime("%Y-%m-%d %H:", timestamp) ||
                CASE
                   WHEN CAST(strftime("%M", timestamp) AS INTEGER) < 20 then "0"
                   WHEN CAST(strftime("%M", timestamp) AS INTEGER) < 40 then "20"
                   ELSE "40"
                END as group_time
            FROM uptime
            WHERE router_name = ?
            ORDER BY timestamp DESC
        )
        SELECT
            MAX(timestamp) as timestamp,
            uptime_seconds
        FROM time_groups
        GROUP BY group_time
        ORDER BY timestamp DESC
        LIMIT 30
    """, (router_name,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        graph_filnavn = "n_data.png"
        graph_filvej = os.path.join("static", graph_filnavn)
        plt.figure(figsize=(8,3), dpi=300)
        plt.text(0.5, 0.5, "Ingen data", fontsize=20, ha="center")
        plt.axis("off")
        plt.savefig(graph_filvej, dpi=300, bbox_inches="tight")
        plt.close()
    else:
        graph_filnavn = uptime_graph(router_name, rows)

    if not rows:
        uptime_final ="Ukendt"
    else:
        uptime_sekunder = rows[0][1]
        dage = uptime_sekunder // 86400
        timer = (uptime_sekunder % 86400) // 3600
        minutter = (uptime_sekunder % 3600) // 60
        sekunder = uptime_sekunder % 60
        uptime_final = f"{dage}d {timer}h {minutter}m {sekunder}s"

    try:
        Hukommelse = int(info.get("Hukommelse", 0))
        Hukommelse_mb = Hukommelse / (1024*1024)
        Hukommelse_info = f"{Hukommelse_mb:.2f} MB"
    except Exception:
        Hukommelse_info = "ukendt"
    
    return render_template("router.html", router={
        "Navn":             r["Navn"],
        "Model":            r["Model"],
        "IP":               r["IP"],
        "Uptime":           uptime_final,
        "Interfaces":       info.get("Interfaces", "Ukendt"),
        "Routingtabel":     info.get("Routingtabel", "Ukendt"),
        "Lokation":         info.get("Lokation", "Ukendt"),
        "Hukommelse":       Hukommelse_info,
        "Genstart_årsag":   info.get("Genstart_årsag", "ukendt"),
        "Temp":             info.get("Temp", "ukendt")
    }, routers=routers, graph_filnavn=graph_filnavn, timestamp=int(datetime.now().timestamp()))

#virker ikke, ved ikke om vi skal gøre noget med den?   
#@app.route("/speedtest")
#def speedtest():
#    if not session.get("loggedin"):
#        return redirect(url_for("login"))
#    try:
#        import speedtest
#        st = speedtest.Speedtest()
#        st.get_best_server()
#        download = st.download() / 1e6
#        upload = st.upload() / 1e6
#        ping = st.results.ping
#        client = 
    
@app.route("/logut")
def logout():
    session.clear()
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(debug=True)
