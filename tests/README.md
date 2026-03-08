# ASOKai Test Suite

Comprehensive test suite for the ASOKai serialization system.

## Test Structure

```
tests/
├── conftest.py                                 # Shared fixtures
├── unit/                                       # Unit tests
│   ├── test_type_registrations.py             # Type registration tests (Seq, Locus)
│   ├── test_serializer.py                     # Serializable base class tests
│   ├── test_genomic_site.py                   # GenomicSite serialization tests
│   ├── test_transcript_site.py                # TranscriptSite serialization tests
│   ├── test_target_gene.py                    # TargetGene serialization tests
│   ├── test_base_site_functionality.py        # Site base class tests
│   ├── test_genomic_site_functionality.py     # GenomicSite functional tests
│   ├── test_transcript_site_functionality.py  # TranscriptSite functional tests
│   ├── test_target_functionality.py           # Target and TargetGene tests
│   ├── test_target_creator_functionality.py   # TargetCreator base class tests
│   └── test_target_gene_creator_functionality.py # TargetGeneCreator tests
└── integration/                                # Integration tests
    └── test_serialization_integration.py      # Complete workflow tests
```

## Running Tests

### Install pytest

```bash
pip install pytest pytest-cov
```

### Run all tests

```bash
pytest
```

### Run with coverage

```bash
pytest --cov=ASOkai --cov-report=html
```

### Run specific test categories

```bash
# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration

# Run only serialization tests
pytest -m serialization
```

### Run specific test files

```bash
pytest tests/unit/test_type_registrations.py
pytest tests/unit/test_genomic_site.py
pytest tests/integration/test_serialization_integration.py
```

### Run specific test classes or functions

```bash
pytest tests/unit/test_serializer.py::TestSerializableBasics
pytest tests/unit/test_genomic_site.py::TestGenomicSiteRoundtrip::test_roundtrip_preserves_data
```

### Verbose output

```bash
pytest -v
```

### Show print statements

```bash
pytest -s
```

## Test Coverage

The test suite covers:

### Unit Tests

#### Serialization Tests

1. **Type Registrations** (`test_type_registrations.py`)
   - Bio.Seq.Seq serialization/deserialization
   - GenomeUtils.Locus flatten functionality
   - Roundtrip consistency

2. **Serializable Base Class** (`test_serializer.py`)
   - Basic to_dict/from_dict operations
   - _non_serializable_attrs exclusions
   - Name mapping (_sequence -> sequence)
   - File I/O (to_file/from_file)
   - Complex nested types (dicts, lists)
   - Registered types in containers

3. **GenomicSite Serialization** (`test_genomic_site.py`)
   - Locus flattening in serialization
   - Locus reconstruction in deserialization
   - Sequence handling
   - Multiple sites in dictionaries
   - Complete roundtrip

4. **TranscriptSite Serialization** (`test_transcript_site.py`)
   - Transcript ID and coordinate serialization
   - Sequence handling
   - Auto-generated ID serialization
   - Multiple sites in dictionaries
   - Complete roundtrip

5. **TargetGene Serialization** (`test_target_gene.py`)
   - Gene attribute serialization
   - Nested sites preservation
   - Name mapping for _sequence and _sites -> sites
   - Large numbers of sites
   - Complete roundtrip

#### Functional Tests

6. **Site Base Class** (`test_base_site_functionality.py`)
   - Site initialization and properties
   - Sequence property
   - Additional kwargs handling
   - Name mapping for _sequence

7. **GenomicSite Functionality** (`test_genomic_site_functionality.py`)
   - Initialization with locus components
   - Automatic ID generation from locus
   - Locus property and direct coordinate access
   - Sites on different chromosomes/strands
   - Edge cases (minimum start, large coordinates, special chr names, length mismatch)

8. **TranscriptSite Functionality** (`test_transcript_site_functionality.py`)
   - Initialization with transcript coordinates
   - Automatic ID generation
   - Coordinate handling (0-based, exclusive end)
   - Overlapping and adjacent sites
   - Sequence operations
   - to_genomic method (placeholder)

9. **Target and TargetGene Functionality** (`test_target_functionality.py`)
   - Target base class initialization
   - Site management (site_by_id, sites property)
   - TargetGene initialization with gene attributes
   - Accessing sites from TargetGene
   - Many sites handling
   - Edge cases (special characters, mitochondrial chr, large coordinates)

10. **TargetCreator Base Class** (`test_target_creator_functionality.py`)
   - Site ID generator functionality
   - ID format with extra prefix parts
   - Custom start numbers
   - Zero padding in IDs
   - Multiple independent generators
   - Abstract method validation (from_file, from_genome)
   - Class attributes (SITE_ID_PREFIX_PARTS)

11. **TargetGeneCreator** (`test_target_gene_creator_functionality.py`)
   - Inheritance of SITE_ID_PREFIX_PARTS
   - Gene-specific site ID generation
   - Method implementations (from_genome, from_file)

### Integration Tests

1. **Complete Workflows** (`test_serialization_integration.py`)
   - Full roundtrip with complex data (50+ sites)
   - File I/O with large datasets
   - JSON structure validation (flattened locus)
   - Multiple save/load cycles
   - Special characters in strings

2. **Backward Compatibility**
   - Missing optional attributes
   - Empty sites

3. **Performance**
   - Large gene serialization (1000 sites)
   - File size validation

4. **Data Validation**
   - Reconstructed objects are functional
   - Locus and Seq methods work correctly

## Test Markers

- `@pytest.mark.unit` - Unit tests
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.serialization` - Serialization-related tests

## Fixtures

Available in `conftest.py`:

- `sample_sequence` - Sample Bio.Seq.Seq object
- `sample_locus` - Sample GenomeUtils.Locus object
- `locus_components` - Locus components as dict
- `temp_json_file` - Temporary JSON file path
- `temp_dir` - Temporary directory

## Expected Test Results

All tests should pass. The suite validates:

1. ✅ Locus components are flattened at top level (no nested `locus` key)
2. ✅ Deserialization correctly maps flattened components to `__init__` parameters
3. ✅ All data (gene, sites, sequences) survives roundtrip
4. ✅ Excluded attributes (_genome, _parent, _children) are not serialized
5. ✅ Registered types (Seq, Locus) work correctly
6. ✅ Complex nested structures are preserved

## Continuous Integration

To run tests in CI:

```yaml
- name: Run tests
  run: |
    pip install -r requirements.txt
    pip install pytest pytest-cov
    pytest --cov=ASOkai --cov-report=xml
```
