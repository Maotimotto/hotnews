#!/bin/bash
# 检查服务器文件权限的脚本

echo "=== 检查文件权限 ==="
ls -la profiles.csv
ls -la output/

echo ""
echo "=== 检查目录权限 ==="
ls -ld .
ls -ld output/

echo ""
echo "=== 检查当前用户 ==="
whoami
id

echo ""
echo "=== 测试写入权限 ==="
touch test_write.tmp && echo "✓ 根目录可写" || echo "✗ 根目录不可写"
touch output/test_write.tmp && echo "✓ output目录可写" || echo "✗ output目录不可写"
rm -f test_write.tmp output/test_write.tmp

echo ""
echo "=== 检查 Python 环境 ==="
which python3
python3 --version

echo ""
echo "=== 检查依赖包 ==="
python3 -c "import httpx; print('✓ httpx')" 2>&1
python3 -c "import markdown; print('✓ markdown')" 2>&1
python3 -c "import bs4; print('✓ beautifulsoup4')" 2>&1
