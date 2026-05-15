import sys

def analyze():
    with open('app.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()

    routes = []
    current_route = None
    start_line = 0

    for i, line in enumerate(lines):
        if line.strip().startswith('@app.route('):
            current_route = line.strip()
            start_line = i + 1
        elif line.strip().startswith('def ') and current_route:
            func_name = line.strip().split('def ')[1].split('(')[0]
            routes.append({
                'route': current_route,
                'func': func_name,
                'line': start_line
            })
            current_route = None
            
    for r in routes:
        print(f"Line {r['line']}: {r['func']} - {r['route']}")

if __name__ == '__main__':
    analyze()
