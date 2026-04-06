from flask import Flask, jsonify, render_template

from network_scanner import NetworkScanner


app = Flask(__name__)
scanner = NetworkScanner()


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/scan")
def scan_network():
    try:
        result = scanner.scan()
        return jsonify(result)
    except Exception as exc:
        return (
            jsonify(
                {
                    "success": False,
                    "error": str(exc),
                    "devices": [],
                    "scanned_subnets": [],
                }
            ),
            500,
        )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
