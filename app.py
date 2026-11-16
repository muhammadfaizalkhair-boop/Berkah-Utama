import sqlite3
import os
import shutil
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from functools import wraps

app = Flask(__name__)
app.secret_key = 'berkah_utama_rahasia'

# Cek apakah sedang jalan di server Vercel
if os.environ.get('VERCEL'):
    DB_NAME = '/tmp/berkah_utama.db'
    if not os.path.exists(DB_NAME) and os.path.exists('berkah_utama.db'):
        shutil.copy('berkah_utama.db', DB_NAME)
else:
    DB_NAME = 'berkah_utama.db'

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row 
    return conn

def init_db():
    is_new = not os.path.exists(DB_NAME)
    conn = get_db_connection()
    if is_new:
        # Tabel barang dengan Kategori & Satuan
        conn.execute('''CREATE TABLE barang (
            id_barang INTEGER PRIMARY KEY AUTOINCREMENT,
            nama_barang TEXT NOT NULL,
            kategori TEXT NOT NULL,
            satuan TEXT NOT NULL,
            harga INTEGER NOT NULL,
            stok INTEGER NOT NULL
        )''')
        conn.execute('''CREATE TABLE penjualan (
            id_penjualan INTEGER PRIMARY KEY AUTOINCREMENT,
            waktu_transaksi TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            total_harga INTEGER NOT NULL,
            metode_pembayaran TEXT NOT NULL,
            status_pesanan TEXT DEFAULT 'Pesanan Berhasil',
            nama_pembeli TEXT DEFAULT 'Pelanggan Toko',
            no_hp TEXT DEFAULT '-',
            alamat_pembeli TEXT DEFAULT 'Belanja di Toko'
        )''')
        conn.execute('''CREATE TABLE detail_penjualan (
            id_detail INTEGER PRIMARY KEY AUTOINCREMENT,
            id_penjualan INTEGER,
            id_barang INTEGER,
            jumlah_beli INTEGER NOT NULL,
            subtotal INTEGER NOT NULL,
            FOREIGN KEY (id_penjualan) REFERENCES penjualan(id_penjualan),
            FOREIGN KEY (id_barang) REFERENCES barang(id_barang)
        )''')
        
        # Data awal lengkap dengan kategori dan satuan
        items = [
            ('Beras Premium 5kg', 'Makanan Pokok', 'Karung', 65000, 20),
            ('Minyak Goreng 2L', 'Sembako', 'Liter', 34000, 15),
            ('Gula Pasir 1kg', 'Makanan Pokok', 'Kg', 16000, 30),
            ('Telur Ayam 1 Papan', 'Protein', 'Papan', 45000, 5),
            ('Tepung Terigu 1kg', 'Makanan Pokok', 'Kg', 12000, 25),
            ('Indomie Goreng 1 Dus', 'Makanan Instan', 'Dus', 115000, 10),
            ('Susu Kental Manis', 'Minuman', 'Kaleng', 12000, 40),
            ('Kopi Kapal Api', 'Minuman', 'Sachet', 25000, 20),
            ('Teh Celup Sosro', 'Minuman', 'Kotak', 6000, 50),
            ('Garam Halus', 'Bumbu Dapur', 'Bungkus', 3000, 60),
            ('Margarin Blue Band', 'Bumbu Dapur', 'Sachet', 10000, 30),
            ('Kecap Bango', 'Bumbu Dapur', 'Botol', 22000, 20),
            ('Saus Sambal ABC', 'Bumbu Dapur', 'Botol', 15000, 25),
            ('Sarden ABC', 'Makanan Instan', 'Kaleng', 21000, 15),
            ('Sabun Sunlight', 'Pembersih', 'Pcs', 11000, 3)
        ]
        for item in items:
            conn.execute('INSERT INTO barang (nama_barang, kategori, satuan, harga, stok) VALUES (?, ?, ?, ?, ?)', 
                         (item[0], item[1], item[2], item[3], item[4]))
        conn.commit()
    else:
        # Migrasi otomatis jika berkah_utama.db lama sudah ada
        kolom_ada = [row[1] for row in conn.execute("PRAGMA table_info(penjualan)").fetchall()]
        if 'status_pesanan' not in kolom_ada:
            conn.execute("ALTER TABLE penjualan ADD COLUMN status_pesanan TEXT DEFAULT 'Pesanan Berhasil'")
        if 'nama_pembeli' not in kolom_ada:
            conn.execute("ALTER TABLE penjualan ADD COLUMN nama_pembeli TEXT DEFAULT 'Pelanggan Toko'")
        if 'no_hp' not in kolom_ada:
            conn.execute("ALTER TABLE penjualan ADD COLUMN no_hp TEXT DEFAULT '-'")
        if 'alamat_pembeli' not in kolom_ada:
            conn.execute("ALTER TABLE penjualan ADD COLUMN alamat_pembeli TEXT DEFAULT 'Belanja di Toko'")
        conn.commit()
    conn.close()

with app.app_context():
    init_db()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    conn = get_db_connection()
    barang_list = conn.execute('SELECT * FROM barang WHERE stok > 0').fetchall()
    conn.close()
    return render_template('index.html', barang=barang_list)

@app.route('/api/checkout', methods=['POST'])
def api_checkout():
    data = request.get_json()
    nama = data.get('nama', 'Pelanggan Online')
    phone = data.get('phone', '-')
    alamat = data.get('alamat', '-')
    metode = data.get('metode', 'QRIS')
    items = data.get('items', [])
    total = int(data.get('total', 0))

    if not items:
        return jsonify({'status': 'error', 'message': 'Keranjang belanja masih kosong!'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    status_awal = 'Pesanan Diproses' if metode == 'COD (Bayar di Tempat)' else 'Menunggu Pembayaran'
    metode_label = f"Online - {metode}"

    cursor.execute('''
        INSERT INTO penjualan (total_harga, metode_pembayaran, status_pesanan, nama_pembeli, no_hp, alamat_pembeli)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (total, metode_label, status_awal, nama, phone, alamat))
    
    id_penjualan = cursor.lastrowid
    kode_trx = f"TRX-{id_penjualan:03d}"

    for item in items:
        barang_db = cursor.execute('SELECT id_barang, stok FROM barang WHERE nama_barang = ?', (item['nama'],)).fetchone()
        if barang_db:
            id_barang = barang_db['id_barang']
            jumlah_beli = int(item['jumlah'])
            subtotal = int(item['harga']) * jumlah_beli
            cursor.execute('''
                INSERT INTO detail_penjualan (id_penjualan, id_barang, jumlah_beli, subtotal)
                VALUES (?, ?, ?, ?)
            ''', (id_penjualan, id_barang, jumlah_beli, subtotal))
            cursor.execute('UPDATE barang SET stok = MAX(0, stok - ?) WHERE id_barang = ?', (jumlah_beli, id_barang))

    conn.commit()
    conn.close()

    return jsonify({
        'status': 'success',
        'id_penjualan': id_penjualan,
        'kode_trx': kode_trx,
        'status_pesanan': status_awal
    })

@app.route('/api/lacak/<kode>')
def api_lacak(kode):
    clean_kode = kode.strip().upper().replace('TRX-', '')
    conn = get_db_connection()
    transaksi = None

    if clean_kode.isdigit():
        transaksi = conn.execute('SELECT * FROM penjualan WHERE id_penjualan = ?', (int(clean_kode),)).fetchone()
    
    if not transaksi:
        transaksi = conn.execute('SELECT * FROM penjualan WHERE no_hp = ? ORDER BY id_penjualan DESC LIMIT 1', (kode.strip(),)).fetchone()

    if not transaksi:
        conn.close()
        return jsonify({'status': 'not_found', 'message': 'Pesanan tidak ditemukan. Periksa kembali Nomor Pesanan atau No. WhatsApp Anda.'}), 404

    details = conn.execute('''
        SELECT d.jumlah_beli, d.subtotal, b.nama_barang, b.satuan
        FROM detail_penjualan d
        JOIN barang b ON d.id_barang = b.id_barang
        WHERE d.id_penjualan = ?
    ''', (transaksi['id_penjualan'],)).fetchall()
    conn.close()

    daftar_item = [
        f"{d['nama_barang']} ({d['jumlah_beli']} {d['satuan']}) - Rp {d['subtotal']:,}".replace(',', '.')
        for d in details
    ]

    return jsonify({
        'status': 'success',
        'kode_trx': f"TRX-{transaksi['id_penjualan']:03d}",
        'nama_pembeli': transaksi['nama_pembeli'],
        'alamat_pembeli': transaksi['alamat_pembeli'],
        'waktu_transaksi': transaksi['waktu_transaksi'],
        'metode_pembayaran': transaksi['metode_pembayaran'],
        'status_pesanan': transaksi['status_pesanan'],
        'total_harga': transaksi['total_harga'],
        'items': daftar_item
    })

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == 'admin' and password == 'admin123':
            session['logged_in'] = True
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error='Username atau Password salah!')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db_connection()
    penjualan = conn.execute('SELECT * FROM penjualan ORDER BY waktu_transaksi DESC, id_penjualan DESC').fetchall()
    total_pendapatan = conn.execute('SELECT SUM(total_harga) FROM penjualan').fetchone()[0] or 0
    barang_menipis = conn.execute('SELECT * FROM barang WHERE stok < 10').fetchall()
    
    # Ambil detail item untuk setiap transaksi (untuk fitur Modal Popup Detail)
    riwayat_transaksi = []
    for p in penjualan:
        details = conn.execute('''
            SELECT d.*, b.nama_barang, b.satuan 
            FROM detail_penjualan d 
            JOIN barang b ON d.id_barang = b.id_barang 
            WHERE d.id_penjualan = ?
        ''', (p['id_penjualan'],)).fetchall()
        riwayat_transaksi.append({
            'penjualan': p,
            'details': details
        })
        
    conn.close()
    return render_template('laporan.html', riwayat=riwayat_transaksi, total=total_pendapatan, barang_menipis=barang_menipis)

@app.route('/update_status/<int:id_penjualan>', methods=['POST'])
@login_required
def update_status(id_penjualan):
    status_baru = request.form['status_pesanan']
    conn = get_db_connection()
    conn.execute('UPDATE penjualan SET status_pesanan = ? WHERE id_penjualan = ?', (status_baru, id_penjualan))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/kasir', methods=['GET', 'POST'])
@login_required
def kasir():
    conn = get_db_connection()
    if request.method == 'POST':
        id_barang = request.form['id_barang']
        jumlah_beli = int(request.form['jumlah_beli'])
        metode = request.form['metode_pembayaran']
        
        if metode == 'Transfer Bank':
            bank_pilihan = request.form.get('bank_pilihan', 'Lainnya')
            metode = f"Transfer Bank ({bank_pilihan})"
        elif metode == 'E-Wallet':
            wallet_pilihan = request.form.get('bank_pilihan', 'Lainnya')
            metode = f"E-Wallet ({wallet_pilihan})"
            
        item = conn.execute('SELECT * FROM barang WHERE id_barang = ?', (id_barang,)).fetchone()
        
        if item and item['stok'] >= jumlah_beli:
            total_harga = item['harga'] * jumlah_beli
            cursor = conn.execute(
                'INSERT INTO penjualan (total_harga, metode_pembayaran, status_pesanan, nama_pembeli, alamat_pembeli) VALUES (?, ?, ?, ?, ?)',
                (total_harga, metode, 'Pesanan Berhasil', 'Pelanggan Kasir (Offline)', 'Belanja di Toko')
            )
            id_penjualan = cursor.lastrowid
            conn.execute('INSERT INTO detail_penjualan (id_penjualan, id_barang, jumlah_beli, subtotal) VALUES (?, ?, ?, ?)', 
                         (id_penjualan, id_barang, jumlah_beli, total_harga))
            conn.execute('UPDATE barang SET stok = stok - ? WHERE id_barang = ?', (jumlah_beli, id_barang))
            conn.commit()
            conn.close()
            return redirect(url_for('struk', id_penjualan=id_penjualan))

    barang = conn.execute('SELECT * FROM barang WHERE stok > 0').fetchall()
    conn.close()
    return render_template('kasir.html', barang=barang)

@app.route('/struk/<int:id_penjualan>')
@login_required
def struk(id_penjualan):
    conn = get_db_connection()
    transaksi = conn.execute('SELECT * FROM penjualan WHERE id_penjualan = ?', (id_penjualan,)).fetchone()
    detail = conn.execute('''
        SELECT d.*, b.nama_barang, b.harga, b.satuan 
        FROM detail_penjualan d 
        JOIN barang b ON d.id_barang = b.id_barang 
        WHERE d.id_penjualan = ?
    ''', (id_penjualan,)).fetchone()
    conn.close()
    return render_template('struk.html', transaksi=transaksi, detail=detail)

@app.route('/barang', methods=['GET', 'POST'])
@login_required
def barang():
    conn = get_db_connection()
    if request.method == 'POST':
        nama = request.form['nama_barang']
        kategori = request.form['kategori']
        satuan = request.form['satuan']
        harga = request.form['harga']
        stok = request.form['stok']
        conn.execute('INSERT INTO barang (nama_barang, kategori, satuan, harga, stok) VALUES (?, ?, ?, ?, ?)', 
                     (nama, kategori, satuan, harga, stok))
        conn.commit()
        return redirect(url_for('barang'))
        
    barang_list = conn.execute('SELECT * FROM barang').fetchall()
    conn.close()
    return render_template('barang.html', barang=barang_list)

@app.route('/restock_barang/<int:id_barang>', methods=['POST'])
@login_required
def restock_barang(id_barang):
    tambah_stok = int(request.form['tambah_stok'])
    conn = get_db_connection()
    conn.execute('UPDATE barang SET stok = stok + ? WHERE id_barang = ?', (tambah_stok, id_barang))
    conn.commit()
    conn.close()
    return redirect(url_for('barang'))

@app.route('/hapus_barang/<int:id_barang>', methods=['POST'])
@login_required
def hapus_barang(id_barang):
    conn = get_db_connection()
    conn.execute('DELETE FROM barang WHERE id_barang = ?', (id_barang,))
    conn.commit()
    conn.close()
    return redirect(url_for('barang'))

@app.route('/hapus_transaksi/<int:id_penjualan>', methods=['POST'])
@login_required
def hapus_transaksi(id_penjualan):
    conn = get_db_connection()
    conn.execute('DELETE FROM detail_penjualan WHERE id_penjualan = ?', (id_penjualan,))
    conn.execute('DELETE FROM penjualan WHERE id_penjualan = ?', (id_penjualan,))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(debug=True)
