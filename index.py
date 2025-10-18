import os
import shutil

# 1. Create the 'api' directory
os.makedirs('api', exist_ok=True)

# 2. Move and rename your application file
# (app.py is the name of your file)
if os.path.exists('app.py'):
	shutil.move('app.py', 'api/index.py')

# 3. Delete the unnecessary, conflicting vercel.json file
if os.path.exists('vercel.json'):
	os.remove('vercel.json')