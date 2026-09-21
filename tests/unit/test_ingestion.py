import pytest
from core.ingestion.parser import parse_source_file

def test_parse_source_notes():
    # Use the provided examples/source-notes.md
    doc = parse_source_file("examples/source-notes.md")
    
    assert doc.metadata.experiment_number == "3"
    assert doc.metadata.title == "Experiment 3"
    assert doc.metadata.co_mapping == "CO2,CO3"
    assert "Design Java programs showcasing exception handling" in doc.metadata.aim
    
    assert doc.easy is not None
    assert "calculate the square root" in doc.easy.problem_statement
    assert "import java.util.Scanner" in doc.easy.code
    
    assert doc.medium is not None
    assert "simulate an ATM withdrawal system" in doc.medium.problem_statement
    assert "class InvalidPinException extends Exception" in doc.medium.code
    
    assert doc.hard is not None
    assert "university enrollment system" in doc.hard.problem_statement
    assert "class CourseFullException extends Exception" in doc.hard.code
    
    assert "To learn about concept of Inheritance" in doc.objectives
    assert "Minimum 384MB RAM" in doc.apparatus
    assert "Abstract Classes and Methods" in doc.reading_material
