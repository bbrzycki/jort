import setuptools

__version__ = '1.2.0'

with open('README.md', 'r') as fh:
    long_description = fh.read()

entry_points = {
    'console_scripts': [
        'jort = jort.jort_exe:main'
    ]
}

with open("requirements.txt", "r") as f:
    install_requires = f.readlines()

setuptools.setup(
    name='jort',
    version=__version__,
    author='Bryan Brzycki',
    author_email='bbrzycki@berkeley.edu',
    description='Script profiler with checkpoints',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/bbrzycki/jort',
    project_urls={
        'Source': 'https://github.com/bbrzycki/jort'
    },
    entry_points=entry_points,
    packages=setuptools.find_packages(),
    install_requires=install_requires,
    classifiers=(
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ),
)
