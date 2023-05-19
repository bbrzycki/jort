import setuptools

with open('README.md', 'r') as fh:
    long_description = fh.read()

setuptools.setup(
    name='jort',
    version='0.1.0',
    author='Bryan Brzycki',
    author_email='bbrzycki@berkeley.edu',
    description='Script profiler with checkpoints',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/bbrzycki/jort',
    project_urls={
        'Source': 'https://github.com/bbrzycki/jort'
    },
    packages=setuptools.find_packages(),
#     include_package_data=True,
    install_requires=[
       'numpy>=1.18.1',
       'pyinstaller>=5.11.0',
    ],
    classifiers=(
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ),
)
