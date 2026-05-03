"""
Slide transition management tools for PowerPoint MCP Server.
Implements slide transition and timing capabilities.
"""

from typing import Dict, List, Optional, Any

def register_transition_tools(app, presentations, get_current_presentation_id, validate_parameters, 
                          is_positive, is_non_negative, is_in_range, is_valid_rgb):
    """Register slide transition management tools with the FastMCP app."""
    
    @app.tool()
    def manage_slide_transitions(
        slide_index: int,
        operation: str,
        transition_type: str = None,
        duration: float = 1.0,
        presentation_id: str = None
    ) -> Dict:
        """
        Manage slide transitions and timing.
        
        Args:
            slide_index: Index of the slide (0-based)
            operation: Operation type ("set", "remove", "get")
            transition_type: Type of transition (basic support)
            duration: Duration of transition in seconds
            presentation_id: Optional presentation ID (uses current if not provided)
            
        Returns:
            Dictionary with transition information
        """
        try:
            # Get presentation
            pres_id = presentation_id or get_current_presentation_id()
            if pres_id not in presentations:
                return {"error": "Presentation not found"}
            
            pres = presentations[pres_id]
            
            # Validate slide index
            if not (0 <= slide_index < len(pres.slides)):
                return {"error": f"Slide index {slide_index} out of range"}
            
            slide = pres.slides[slide_index]
            
            if operation == "get":
                # Read the transition XML directly from the slide element.
                # python-pptx has no high-level API; this returns whatever transition
                # node exists, or {} if none.
                from pptx.oxml.ns import qn
                trans = slide.element.find(qn('p:transition'))
                if trans is None:
                    return {
                        "slide_index": slide_index,
                        "transition": None,
                        "message": "No transition set on this slide"
                    }
                return {
                    "slide_index": slide_index,
                    "transition_xml": trans.xml,
                    "message": f"Transition found on slide {slide_index}"
                }

            elif operation in ("set", "remove"):
                # Be honest: python-pptx exposes no API for transitions, and we have
                # not implemented the XML manipulation. Don't return fake success.
                return {
                    "error": "not_implemented",
                    "operation": operation,
                    "slide_index": slide_index,
                    "details": (
                        f"manage_slide_transitions(operation='{operation}') is not implemented. "
                        "python-pptx has no transition API; setting/removing transitions "
                        "requires direct OXML manipulation that this server does not yet do."
                    ),
                }

            else:
                return {"error": f"Unsupported operation: {operation}. Use 'set', 'remove', or 'get'"}
                
        except Exception as e:
            return {"error": f"Failed to manage slide transitions: {str(e)}"}